#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from smart_interfaces.msg import SmartCommand
import json

class SpatialProjectorNode(Node):
    def __init__(self):
        super().__init__('spatial_projector')
        
        self.create_subscription(String, '/ai/vision_targets', self.vision_cb, 10)
        self.create_subscription(String, '/ai/vision_request', self.request_cb, 10)
        
        self.cmd_pub = self.create_publisher(SmartCommand, '/smart_command', 10)
        self.tts_pub = self.create_publisher(String, '/ai/tts_speak', 10)
        
        self.target_class = None
        self.is_searching = False
        self.is_tracking = False
        
        self.get_logger().info("Spatial Projector ready. Waiting for vision requests.")

    def request_cb(self, msg):
        req = msg.data.lower()
        if req == 'stop':
            self.target_class = None
            self.is_searching = False
            self.is_tracking = False
            self.get_logger().info("Vision tracking stopped.")
            return
            
        self.target_class = req
        self.is_searching = True
        self.is_tracking = False
        self.get_logger().info(f"Started search for: {self.target_class}")

    def vision_cb(self, msg):
        if not self.is_searching and not self.is_tracking:
            return
            
        try:
            targets = json.loads(msg.data)
        except Exception as e:
            self.get_logger().error(f"JSON error: {e}")
            return
            
        if not targets:
            return
            
        # Find our target in the detected objects
        target_obj = next((obj for obj in targets if obj['class'].lower() == self.target_class or (self.target_class == 'person' and obj['id'] == 0)), None)
        
        if target_obj:
            if self.is_searching:
                # We just found it! Stop rotation.
                self.is_searching = False
                self.is_tracking = True
                
                stop_cmd = SmartCommand()
                stop_cmd.target_system = 'system'
                stop_cmd.command = 'stop'
                self.cmd_pub.publish(stop_cmd)
                
                tts = String()
                tts.data = f"Вижу {self.target_class}. Подъезжаю."
                self.tts_pub.publish(tts)
                
                self.get_logger().info(f"Target {self.target_class} found! Switching to track mode.")
            
            if self.is_tracking:
                # Send track_target command
                track_cmd = SmartCommand()
                track_cmd.target_system = 'tactical'
                track_cmd.command = 'track_target'
                track_cmd.payload_json = json.dumps({"offset": target_obj['offset']})
                self.cmd_pub.publish(track_cmd)
                
def main():
    rclpy.init()
    node = SpatialProjectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
