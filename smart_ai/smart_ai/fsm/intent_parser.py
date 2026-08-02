import re

class IntentParser:
    def __init__(self):
        # Basic patterns for direct tactical commands
        self.patterns = {
            'stop': r'\b(stop|halt|wait|стоп)\b',
            'go_to': r'\b(go to|head to)\s+(.+)',
            'save_waypoint': r'\b(save waypoint|save point)\s+(.+)',
            'light_on': r'\blight\s+on\b',
            'light_off': r'\blight\s+off\b',
            'forward': r'\bforward\b',
            'back': r'\bback\b',
            'turn': r'\bturn\b'
        }

    def parse(self, text):
        text = text.lower().replace('!', '').replace('?', '').replace("'", "")
        if text.endswith('.'):
            text = text[:-1]

        # Stop command is highest priority
        if re.search(self.patterns['stop'], text):
            return {'intent': 'stop', 'payload': None}

        # Light commands
        if re.search(self.patterns['light_on'], text):
            return {'intent': 'light_on', 'payload': None}
        if re.search(self.patterns['light_off'], text):
            return {'intent': 'light_off', 'payload': None}

        # Check for find/follow objects
        match = re.search(r'\b(?:find|look for)\s+(?:the\s+)?([a-zA-Z\s]+)\b', text)
        if match:
            target = match.group(1).strip()
            return {'intent': 'find_object', 'payload': {'target': target}}
            
        match = re.search(r'\b(?:follow|track)\s+(?:me|person)\b', text)
        if match:
            return {'intent': 'find_object', 'payload': {'target': 'person'}}

        # Waypoint actions
        match = re.search(self.patterns['go_to'], text)
        if match:
            target = match.group(2).strip().replace(' ', '_')
            return {'intent': 'go_to_named', 'payload': {'name': target}}

        match = re.search(self.patterns['save_waypoint'], text)
        if match:
            target = match.group(2).strip().replace(' ', '_')
            return {'intent': 'save_waypoint', 'payload': {'name': target}}

        # Simple movements
        match = re.search(self.patterns['forward'], text)
        if match:
            return {'intent': 'move_relative', 'payload': {'direction': 'forward', 'value': self._get_meters(text)}}
            
        match = re.search(self.patterns['back'], text)
        if match:
            return {'intent': 'move_relative', 'payload': {'direction': 'back', 'value': self._get_meters(text)}}
            
        match = re.search(self.patterns['turn'], text)
        if match:
            deg = self._get_degrees(text)
            if 'right' in text:
                deg = -deg
            elif 'around' in text:
                deg = 180.0
            return {'intent': 'turn_relative', 'payload': {'degrees': deg}}

        # Trigger words for LLM (Strategist)
        trigger_patterns = r'\b(ai|system|robot|analyze)\b'
        if re.search(trigger_patterns, text):
            # Clean up the trigger word if possible, or just pass raw
            return {'intent': 'complex', 'payload': {'raw_text': text}}

        return {'intent': 'unknown', 'payload': None}

    def _get_meters(self, text):
        nums = re.findall(r'\d+\.\d+|\d+', text)
        if nums:
            return float(nums[0])
        text_nums = {
            'one and a half': 1.5, 'two and a half': 2.5, 'half': 0.5,
            'one': 1.0, 'two': 2.0, 'three': 3.0, 'four': 4.0, 'five': 5.0
        }
        for word, val in text_nums.items():
            if word in text: return val
        return 1.0 

    def _get_degrees(self, text):
        nums = re.findall(r'\d+\.\d+|\d+', text)
        if nums:
            return float(nums[0])
        text_nums = {
            'fifteen': 15.0, 'thirty': 30.0, 'forty five': 45.0, 'sixty': 60.0, 
            'ninety': 90.0, 'one eighty': 179.0, 'half': 45.0
        }
        for word, val in text_nums.items():
            if word in text: return val
        return 90.0
