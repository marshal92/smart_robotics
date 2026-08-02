#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty
from smart_interfaces.msg import SmartCommand

class HeartbeatPublisher(Node):
    def __init__(self):
        super().__init__('operator_heartbeat_node')
        self.pub = self.create_publisher(Empty, '/operator_heartbeat', 10)
        self.sub = self.create_subscription(SmartCommand, '/smart_command', self.command_cb, 10)
        self.timer = self.create_timer(0.5, self.timer_callback)
        self.is_active = False
        self.get_logger().info('Pulse Generator started (INACTIVE). Waiting for watchdog_on command...')

    def command_cb(self, msg):
        if msg.target_system == 'system':
            if msg.command == 'watchdog_on':
                self.is_active = True
                self.get_logger().info('Watchdog ON: Started transmitting connection pulses.')
            elif msg.command == 'watchdog_off':
                self.is_active = False
                self.get_logger().info('Watchdog OFF: Stopped transmitting connection pulses.')

    def timer_callback(self):
        if self.is_active:
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