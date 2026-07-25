#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty

class HeartbeatPublisher(Node):
    def __init__(self):
        super().__init__('operator_heartbeat_node')
        self.pub = self.create_publisher(Empty, '/operator_heartbeat', 10)
        self.timer = self.create_timer(0.5, self.timer_callback)
        self.get_logger().info('Pulse Generator started. Transmitting connection...')

    def timer_callback(self):
        self.pub.publish(Empty())

def main(args=None):
    rclpy.init(args=args)
    node = HeartbeatPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()