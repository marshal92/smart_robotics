#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
import json
from .fsm.intent_parser import IntentParser

# Fallback in case smart_interfaces is not fully built yet, 
# though normally we'd import SmartCommand directly.
try:
    from smart_interfaces.msg import SmartCommand
except ImportError:
    # Dummy class for syntax checking if package is missing during early dev
    class SmartCommand:
        def __init__(self):
            self.target_system = ""
            self.command = ""
            self.payload_json = ""

# ROS SETTINGS
VOICE_RAW_TOPIC = '/ai/voice_raw'
COMPLEX_REQUEST_TOPIC = '/ai/complex_request'
SMART_CMD_TOPIC = '/smart_command'
TTS_TOPIC = '/ai/tts_speak'
LIGHT_TOPIC = '/cmd_light' # Direct fallback if not using smart_command for light
VISION_REQ_TOPIC = '/ai/vision_request'

class SemanticDispatcherNode(Node):
    def __init__(self):
        super().__init__('semantic_dispatcher_node')
        
        self.parser = IntentParser()

        # Subscriptions
        self.voice_sub = self.create_subscription(String, VOICE_RAW_TOPIC, self.voice_callback, 10)
        
        # Publishers
        self.complex_pub = self.create_publisher(String, COMPLEX_REQUEST_TOPIC, 10)
        self.smart_cmd_pub = self.create_publisher(SmartCommand, SMART_CMD_TOPIC, 10)
        self.tts_pub = self.create_publisher(String, TTS_TOPIC, 10)
        self.light_pub = self.create_publisher(Bool, LIGHT_TOPIC, 10)
        self.vision_req_pub = self.create_publisher(String, VISION_REQ_TOPIC, 10)

        # FSM State (Basic implementation for now)
        self.state = 'IDLE'

        self.get_logger().info('Semantic Dispatcher Node started. State: IDLE')

    def voice_callback(self, msg):
        text = msg.data
        self.get_logger().info(f"Received voice text: '{text}'")
        
        parsed = self.parser.parse(text)
        intent = parsed['intent']
        payload = parsed['payload']
        
        self.get_logger().info(f"Parsed Intent: {intent}")

        if intent == 'unknown':
            # Ignore noise. Do nothing.
            self.get_logger().info("Intent unknown. Ignoring noise.")
            
        elif intent == 'complex':
            # Complex request with trigger word, forward to Strategist (LLM)
            self.get_logger().info("Trigger detected. Forwarding to LLM Strategist.")
            self.publish_tts("Думаю над задачей.")
            
            req_msg = String()
            req_msg.data = payload['raw_text']
            self.complex_pub.publish(req_msg)
            self.state = 'WAITING_FOR_LLM'
        else:
            # Tactical immediate execution
            self.execute_tactical_intent(intent, payload)

    def execute_tactical_intent(self, intent, payload):
        if intent == 'stop':
            self.publish_smart_command('nav', 'cancel')
            self.publish_tts("Останавливаюсь.")
            
        elif intent == 'light_on':
            msg = Bool(); msg.data = True
            self.light_pub.publish(msg)
            self.publish_tts("Свет включен.")
            
        elif intent == 'light_off':
            msg = Bool(); msg.data = False
            self.light_pub.publish(msg)
            self.publish_tts("Свет выключен.")
            
        elif intent == 'go_to_named':
            target_name = payload['name']
            self.publish_smart_command('nav', 'go_to_named', {"name": target_name})
            self.publish_tts(f"Еду в точку {target_name}.")
            
        elif intent == 'save_waypoint':
            target_name = payload['name']
            self.publish_smart_command('waypoints', 'save', {"name": target_name})
            self.publish_tts(f"Сохраняю точку {target_name}.")
            
        elif intent == 'move_relative':
            dist = payload['value']
            direction = payload['direction']
            
            self.publish_smart_command('tactical', 'move_relative', {"direction": direction, "distance": dist})
            self.publish_tts(f"Двигаюсь {'вперед' if direction == 'forward' else 'назад'} на {abs(dist)} метров.")
            
        elif intent == 'turn_relative':
            degrees = payload['degrees']
            self.publish_smart_command('tactical', 'turn_relative', {"degrees": degrees})
            self.publish_tts(f"Поворачиваю.")
            
        elif intent == 'find_object':
            target = payload['target']
            self.publish_tts(f"Ищу {target}.")
            
            # 1. Ask vision system to start looking for the target
            req_msg = String()
            req_msg.data = target
            self.vision_req_pub.publish(req_msg)
            
            # 2. Tell robot to turn 360 to scan the room
            self.publish_smart_command('tactical', 'turn_relative', {"degrees": 360.0})

    def publish_smart_command(self, target, cmd, payload_dict=None):
        msg = SmartCommand()
        msg.target_system = target
        msg.command = cmd
        if payload_dict:
            msg.payload_json = json.dumps(payload_dict)
        else:
            msg.payload_json = "{}"
            
        self.smart_cmd_pub.publish(msg)
        self.get_logger().info(f"Published SmartCommand -> {target}:{cmd}")

    def publish_tts(self, text):
        msg = String()
        msg.data = text
        self.tts_pub.publish(msg)

def main():
    rclpy.init()
    node = SemanticDispatcherNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
