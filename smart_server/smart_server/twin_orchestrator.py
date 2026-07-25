#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class TwinOrchestrator(Node):
    def __init__(self):
        super().__init__('twin_orchestrator')
        
        self.sub = self.create_subscription(String, '/operator_command', self.command_cb, 10)
        self.shadow_pub = self.create_publisher(String, '/shadow_command', 10)
        
        self.get_logger().info("[Server] Twin Orchestrator started! Waiting for /operator_command...")

    def command_cb(self, msg):
        cmd = msg.data.lower()
        
        if cmd == 'execute':
            self.get_logger().info("[Server] EXECUTE command. Dispatching Shadow route to Nav2...")
            shadow_msg = String()
            shadow_msg.data = 'execute'
            self.shadow_pub.publish(shadow_msg)
            
        elif cmd == 'clear':
            self.get_logger().warn("[Server] CLEAR command! Resetting Shadow.")
            shadow_msg = String()
            shadow_msg.data = 'clear'
            self.shadow_pub.publish(shadow_msg)

def main(args=None):
    rclpy.init(args=args)
    node = TwinOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Stopping Twin Orchestrator...")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()