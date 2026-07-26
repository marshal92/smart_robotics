#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Float32
from nav_msgs.msg import Odometry
from smart_interfaces.msg import SmartTelemetry
import json

class TelemetryMux(Node):
    def __init__(self):
        super().__init__('telemetry_mux')
        
        # Latest State Store
        self.telemetry = SmartTelemetry()
        self.telemetry.fsm_state = "UNKNOWN"
        self.telemetry.nav_status = "IDLE"
        
        # Subscriptions to local Raspberry topics
        self.create_subscription(String, '/fsm_status', self.fsm_cb, 10)
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.create_subscription(Float32, '/current_dose_rate', self.dose_cb, 10)
        self.create_subscription(Bool, '/cmd_light', self.light_cb, 10)
        self.create_subscription(String, '/payload/status', self.payload_cb, 10)
        # TODO: Add a subscription to the Nav2 status once I finish refining the navigation.
        
        # Unified publisher for the bridge
        self.pub = self.create_publisher(SmartTelemetry, '/smart_telemetry', 10)
        
        # We publish 5 times per second
        self.create_timer(0.2, self.timer_cb)
        self.get_logger().info('Telemetry Mux запущен: агрегация данных 5Hz')

    def fsm_cb(self, msg): self.telemetry.fsm_state = msg.data
    def dose_cb(self, msg): self.telemetry.dose_rate = msg.data
    def light_cb(self, msg): self.telemetry.light_is_on = msg.data
    
    def odom_cb(self, msg):
        self.telemetry.linear_speed = msg.twist.twist.linear.x
        self.telemetry.angular_speed = msg.twist.twist.angular.z
        
    def payload_cb(self, msg):
        try:
            data = json.loads(msg.data)
            self.telemetry.active_tools = data.get("active_tools", [])
        except Exception:
            pass

    def timer_cb(self):
        self.telemetry.header.stamp = self.get_clock().now().to_msg()
        self.pub.publish(self.telemetry)

def main():
    rclpy.init()
    node = TelemetryMux()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()