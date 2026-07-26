#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String
from smart_interfaces.msg import SmartCommand

import json
import time
import threading

class PayloadManager(Node):
    def __init__(self):
        super().__init__('payload_manager')
        
        self.active_tools = set()
        
        self.create_subscription(Bool, '/cmd_light', self.light_cb, 10)
        self.create_subscription(SmartCommand, '/smart_command', self.cmd_cb, 10)
        #self.create_subscription(String, '/payload/command', self.cmd_cb, 10)
        
        self.status_pub = self.create_publisher(String, '/payload/status', 10)
        
        self.get_logger().info("Payload Manager activated. Equipment ready.")

    def light_cb(self, msg):
        state = "ON" if msg.data else "OFF"
        self.get_logger().info(f"Light relay: {state}")
        # In future, this will contain code for communicating with the microcontroller (I2C/Serial)

    def cmd_cb(self, msg):
        if msg.target_system != 'payload':
            return
            
        action = msg.command
        
        if action == "mock_sample":
            if "lfcm_drill" not in self.active_tools:
                threading.Thread(target=self._execute_sample, daemon=True).start()
            else:
                self.get_logger().warn("Drill already in use!")

    def _execute_sample(self):
        tool = "lfcm_drill"
        self.active_tools.add(tool)
        self._publish_status()
        
        try:
            self.get_logger().info("[Drill] Starting drilling...")
            time.sleep(2.0)
            self.get_logger().info("[Drill] Calibrating...")
            time.sleep(3.0)
            self.get_logger().info("[Drill] Sample isolated.")
        finally:
            self.active_tools.discard(tool)
            self._publish_status()

    def _publish_status(self):
        msg = String()
        msg.data = json.dumps({"active_tools": list(self.active_tools)})
        self.status_pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = PayloadManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()