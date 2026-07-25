#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool, String
from sensor_msgs.msg import LaserScan

from faster_whisper import WhisperModel
import pyaudio
import wave
import threading
import tempfile
import os
import math
import time
import sys
import tty
import termios
import signal
import re
import json

# ROS SETTINGS
CMD_VEL_TOPIC = '/cmd_vel'
ODOM_TOPIC = '/odom'
LIGHT_TOPIC = '/cmd_light'
SCAN_TOPIC = '/scan' 

MAX_LINEAR_SPEED = 0.5
MIN_LINEAR_SPEED = 0.2
ANGULAR_SPEED = 0.6 

# Lidar Settings
LIDAR_IS_FLIPPED = True  

class WhisperVoiceCommander(Node):
    def __init__(self):
        super().__init__('voice_commander_whisper')
        
        self.cmd_pub = self.create_publisher(Twist, CMD_VEL_TOPIC, 10)
        self.light_pub = self.create_publisher(Bool, LIGHT_TOPIC, 10)
        
        # PUBLISHER FOR WAYPOINT DATABASE (Communication with waypoint_manager)
        self.wp_pub = self.create_publisher(String, '/waypoint_command', 10)
        
        self.odom_sub = self.create_subscription(Odometry, ODOM_TOPIC, self.odom_callback, 10)
        self.scan_sub = self.create_subscription(LaserScan, SCAN_TOPIC, self.scan_callback, 10)
        
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.odom_ready = False
        
        self.busy = False          
        self.emergency_stop = False 
        self.current_direction = 0  
        self.running = True

        self.get_logger().info('Loading Faster-Whisper (CUDA, base.en)...')
        self.model = WhisperModel("base.en", device="cuda", compute_type="float16")
        
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.p = pyaudio.PyAudio()
        
        self.is_recording = False
        self.is_processing = False 
        self.frames = []

        threading.Thread(target=self.terminal_listener, daemon=True).start()

    def get_single_char(self):
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    def terminal_listener(self):
        time.sleep(2) 
        self.unlock_terminal() 
        print("\n" + "="*50)
        print(" READY! Press SPACE (once) to start, again to stop.")
        print("="*50 + "\n")
        
        last_press_time = 0
        
        while self.running and rclpy.ok():
            ch = self.get_single_char()
            current_time = time.time()
            
            if self.is_processing:
                continue
            
            if ch == ' ' and (current_time - last_press_time) > 0.3: 
                last_press_time = current_time
                
                if not self.is_recording:
                    self.is_recording = True
                    self.frames = []
                    print("\n RECORDING... (Say)")
                    threading.Thread(target=self.record_audio, daemon=True).start()
                else:
                    self.is_recording = False
                    self.is_processing = True
                    print("Final processing...")
                    
            elif ch == '\x03': 
                self.running = False
                os.kill(os.getpid(), signal.SIGINT)
                break

    def record_audio(self):
        stream = self.p.open(format=self.format, channels=self.channels,
                             rate=self.rate, input=True,
                             frames_per_buffer=self.chunk)
        
        while self.is_recording:
            try:
                data = stream.read(self.chunk, exception_on_overflow=False)
                self.frames.append(data)
            except Exception:
                pass
            
        stream.stop_stream()
        stream.close()
        self.process_audio_final()

    def process_audio_final(self):
        if len(self.frames) < 5: 
            self.unlock_terminal()
            return

        fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        
        wf = wave.open(temp_path, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.p.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()

        try:
            # Add waypoint commands
            prompt_cheat_sheet = "Robot commands: forward, back, left, right, turn around, degrees, stop, halt, wait, light on, light off, go to base, head to home, save waypoint alpha, one, two, three, four, five meters, half."
            
            segments, _ = self.model.transcribe(
                temp_path, 
                beam_size=3, 
                language="en", 
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
                initial_prompt=prompt_cheat_sheet 
            )
            
            clean_text = " ".join([segment.text for segment in segments]).strip()
            
            if clean_text:
                print(f"Command: '{clean_text}'")
                self.process_text(clean_text)
            else:
                print(' Silence or noise.')
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.unlock_terminal()
            print("-" * 30)

    def unlock_terminal(self):
        self.is_processing = False
        try:
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except Exception:
            pass

    # LOGIC FOR CONTROL AND AUTO-STOP
    
    def scan_callback(self, msg):
        if not self.busy or self.emergency_stop or self.current_direction != 1:
            return
            
        num_ranges = len(msg.ranges)
        if num_ranges < 10:
            return
            
        center_index = num_ranges // 2
        cone_size = int(num_ranges * (20.0 / 360.0))
        
        start_idx = max(0, center_index - cone_size)
        end_idx = min(num_ranges, center_index + cone_size)
        
        front_ranges = msg.ranges[start_idx:end_idx]
        valid_ranges = [r for r in front_ranges if 0.02 < r < 5.0 and not math.isinf(r) and not math.isnan(r)]
        
        if valid_ranges and min(valid_ranges) < 0.5:
            print("\n [LiDAR] Obstacle ahead! Emergency STOP!")
            self.emergency_stop = True
    
    def odom_callback(self, msg):
        self.x = msg.pose.pose.position.x
        self.y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        siny_cosp = 2 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
        self.yaw = math.atan2(siny_cosp, cosy_cosp)
        if not self.odom_ready: self.odom_ready = True

    def get_meters(self, text):
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

    def get_degrees(self, text):
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

    def move_distance(self, target_meters):
        if not self.odom_ready: 
            print("Error: No odometry data available!")
            self.busy = False
            return

        direction_sign = 1.0 if target_meters > 0 else -1.0
        self.current_direction = direction_sign  
        self.emergency_stop = False 
        target_abs = abs(target_meters)
        
        print(f">>> Starting movement for {target_meters} m.")
        start_x = self.x
        start_y = self.y
        twist = Twist()
        timeout_start = time.time()
        
        try:
            while rclpy.ok() and self.running:
                if self.emergency_stop:
                    print("! EMERGENCY STOP !")
                    break
                    
                if time.time() - timeout_start > (target_abs / MIN_LINEAR_SPEED + 10.0):
                    print(" [TIMEOUT] Movement is taking too long. Cancelling.")
                    break

                dx = self.x - start_x
                dy = self.y - start_y
                dist_moved = math.hypot(dx, dy)
                remaining = target_abs - dist_moved
                
                if remaining <= 0.02:
                    print(">>> Target reached.")
                    break
                
                speed = (remaining / 0.5) * MAX_LINEAR_SPEED if remaining < 0.5 else MAX_LINEAR_SPEED
                twist.linear.x = max(speed, MIN_LINEAR_SPEED) * direction_sign
                twist.angular.z = 0.0
                self.cmd_pub.publish(twist)
                time.sleep(0.1)
        finally:
            self.stop_robot()
            self.busy = False 
            self.current_direction = 0 

    def turn_robot(self, target_angle_deg):
        if not self.odom_ready: 
            print("Error: No odometry data available!")
            self.busy = False
            return

        self.current_direction = 0 
        self.emergency_stop = False
        print(f">>> Turning by {target_angle_deg} degrees.")
        
        target_rad = math.radians(abs(target_angle_deg))
        direction = 1 if target_angle_deg > 0 else -1
        
        twist = Twist()
        twist.angular.z = ANGULAR_SPEED * direction
        last_yaw = self.yaw
        total_turned = 0.0
        timeout_start = time.time()
        
        try:
            while rclpy.ok() and self.running:
                if self.emergency_stop:
                    print("! EMERGENCY STOP (turning) !")
                    break
                    
                if time.time() - timeout_start > 15.0:
                    print(" [TIMEOUT] Turning is taking too long. Cancelling.")
                    break

                current_yaw = self.yaw
                delta = current_yaw - last_yaw
                
                if delta > math.pi: delta -= 2 * math.pi
                elif delta < -math.pi: delta += 2 * math.pi
                
                total_turned += abs(delta)
                last_yaw = current_yaw
                
                if total_turned >= target_rad:
                    print(">>> Turning completed.")
                    break
                    
                self.cmd_pub.publish(twist)
                time.sleep(0.1)
        finally:
            self.stop_robot()
            self.busy = False

    def stop_robot(self):
        msg = Twist()
        for _ in range(3):
            self.cmd_pub.publish(msg)
            time.sleep(0.05)

    def set_light(self, state):
        msg = Bool()
        msg.data = state
        self.light_pub.publish(msg)
        print(f">>> Light: {state}")

    def process_text(self, text):
        text = text.lower().replace('!', '').replace('?', '').replace("'", "")
        text = re.sub(r'(\d),(\d)', r'\1.\2', text)
        if text.endswith('.'):
            text = text[:-1]
        
        if 'stop' in text or 'halt' in text or 'wait' in text or 'стоп' in text:
            print("! Received STOP command !")
            self.emergency_stop = True
            self.busy = False 
            self.stop_robot()
            return 

        if self.busy:
            print(f"...ignoring '{text}', robot is busy...")
            return

        # VOICE COMMANDS FOR NAVIGATION
        if 'go to' in text or 'head to' in text:
            if 'go to' in text:
                target_str = text.split('go to')[-1].strip()
            else:
                target_str = text.split('head to')[-1].strip()
            
            target_name = target_str.replace(' ', '_')
            if target_name:
                cmd = json.dumps({"action": "go_to_named", "name": target_name})
                self.wp_pub.publish(String(data=cmd))
                print(f" Sending command to Waypoint Manager: Go to waypoint '{target_name.upper()}'")
            return
            
        elif 'save waypoint' in text or 'save point' in text:
            if 'save waypoint' in text:
                target_str = text.split('save waypoint')[-1].strip()
            else:
                target_str = text.split('save point')[-1].strip()
                
            target_name = target_str.replace(' ', '_')
            if target_name:
                cmd = json.dumps({
                    "action": "save",
                    "name": target_name,
                    "x": self.x,
                    "y": self.y,
                    "yaw": self.yaw
                })
                self.wp_pub.publish(String(data=cmd))
                print(f"🎤 Sending command to Waypoint Manager: Save coordinates as '{target_name.upper()}'")
            return
        # ---------------------------------

        if 'light' in text and 'on' in text:
            self.set_light(True)
        elif 'light' in text and 'off' in text:
            self.set_light(False)
            
        elif 'forward' in text:
            meters = self.get_meters(text)
            self.busy = True 
            threading.Thread(target=self.move_distance, args=(meters,)).start()
            
        elif 'back' in text:
            meters = self.get_meters(text)
            self.busy = True
            threading.Thread(target=self.move_distance, args=(-meters,)).start()
            
        elif 'turn' in text:
            deg = self.get_degrees(text)
            if 'right' in text:
                deg = -deg
            elif 'around' in text:
                deg = 179.0
            
            self.busy = True
            threading.Thread(target=self.turn_robot, args=(deg,)).start()

def main():
    rclpy.init()
    node = WhisperVoiceCommander()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.running = False
        node.stop_robot()
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, termios.tcgetattr(sys.stdin.fileno()))
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()