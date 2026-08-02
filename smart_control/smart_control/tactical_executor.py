#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from smart_interfaces.msg import SmartCommand
import math
import time
import json

class TacticalExecutorNode(Node):
    def __init__(self):
        super().__init__('tactical_executor')
        
        # Publishers and Subscribers
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.telemetry_pub = self.create_publisher(String, '/smart_telemetry', 10) # Mock telemetry status
        
        self.create_subscription(SmartCommand, '/smart_command', self.cmd_cb, 10)
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.create_subscription(LaserScan, '/scan', self.scan_cb, 10)
        
        # State
        self.is_busy = False
        self.emergency_stop = False
        self.task_type = None  # 'move' or 'turn'
        self.target_value = 0.0
        self.start_x = 0.0
        self.start_y = 0.0
        self.start_yaw = 0.0
        self.direction = 1.0 # 1.0 forward, -1.0 backward
        
        # Odometry
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_yaw = 0.0
        self.odom_ready = False
        
        # Control parameters
        self.MAX_LINEAR = 0.3
        self.MIN_LINEAR = 0.1
        self.ANGULAR_SPEED = 0.5
        self.SAFETY_DIST = 0.5

        self.get_logger().info("Tactical Executor Node ready. Waiting for /smart_command (tactical).")

    def odom_cb(self, msg):
        self.current_x = msg.pose.pose.position.x
        self.current_y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        siny_cosp = 2 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
        self.current_yaw = math.atan2(siny_cosp, cosy_cosp)
        if not self.odom_ready:
            self.odom_ready = True

    def scan_cb(self, msg):
        if not self.is_busy and self.task_type != 'track':
            return
            
        if self.task_type == 'move' and self.direction < 0:
            return
            
        # Check cone in front
        num_ranges = len(msg.ranges)
        if num_ranges < 10: return
        
        center = num_ranges // 2
        cone = int(num_ranges * (20.0 / 360.0))
        
        front_ranges = msg.ranges[max(0, center-cone) : min(num_ranges, center+cone)]
        valid_ranges = [r for r in front_ranges if 0.02 < r < 4.0 and not math.isinf(r) and not math.isnan(r)]
        
        if valid_ranges and min(valid_ranges) < self.SAFETY_DIST:
            if not self.emergency_stop:
                self.get_logger().warn("OBSTACLE DETECTED! Emergency Stop.")
                self.emergency_stop = True

    def cmd_cb(self, msg):
        if msg.target_system != 'tactical':
            return
            
        if self.is_busy:
            self.get_logger().warn("Busy executing a tactical command. Ignoring new request.")
            return

        payload = {}
        if msg.payload_json:
            try: payload = json.loads(msg.payload_json)
            except Exception as e: self.get_logger().error(f"JSON Parse error: {e}")

        if msg.command == 'move_relative':
            dist = float(payload.get('distance', 1.0))
            direction = payload.get('direction', 'forward')
            self.execute_move(dist, direction)
            
        elif msg.command == 'turn_relative':
            deg = float(payload.get('degrees', 90.0))
            self.execute_turn(deg)
            
        elif msg.command == 'track_target':
            offset = float(payload.get('offset', 0.0))
            self.execute_track(offset)

    def stop_robot(self):
        msg = Twist()
        for _ in range(3):
            self.cmd_vel_pub.publish(msg)
            time.sleep(0.05)

    def execute_move(self, distance, direction_str):
        if not self.odom_ready:
            self.get_logger().error("Cannot move: No odometry.")
            return
            
        self.is_busy = True
        self.emergency_stop = False
        self.task_type = 'move'
        self.target_value = abs(distance)
        self.direction = 1.0 if direction_str == 'forward' else -1.0
        
        self.start_x = self.current_x
        self.start_y = self.current_y
        
        self.get_logger().info(f"Starting tactical move: {distance}m {direction_str}")
        
        # We run the loop in a timer rather than blocking thread to keep ROS spinning nicely
        # But for a quick script, a threaded approach or just a simple timer works.
        # Since rclpy.spin() is running the main thread, blocking here blocks callbacks!
        # We must use a Timer.
        self.timer = self.create_timer(0.05, self.move_loop)
        
    def move_loop(self):
        if self.emergency_stop:
            self.stop_robot()
            self.is_busy = False
            self.timer.cancel()
            self.get_logger().info("Move aborted due to emergency stop.")
            return

        dx = self.current_x - self.start_x
        dy = self.current_y - self.start_y
        dist_moved = math.hypot(dx, dy)
        remaining = self.target_value - dist_moved
        
        if remaining <= 0.05:
            self.stop_robot()
            self.is_busy = False
            self.timer.cancel()
            self.get_logger().info("Move completed successfully.")
            return
            
        speed = (remaining / 0.5) * self.MAX_LINEAR if remaining < 0.5 else self.MAX_LINEAR
        speed = max(speed, self.MIN_LINEAR)
        
        msg = Twist()
        msg.linear.x = speed * self.direction
        self.cmd_vel_pub.publish(msg)

    def execute_turn(self, degrees):
        if not self.odom_ready:
            self.get_logger().error("Cannot turn: No odometry.")
            return
            
        self.is_busy = True
        self.emergency_stop = False
        self.task_type = 'turn'
        self.target_value = math.radians(abs(degrees))
        self.direction = 1.0 if degrees > 0 else -1.0
        
        self.start_yaw = self.current_yaw
        self.turned_so_far = 0.0
        
        self.get_logger().info(f"Starting tactical turn: {degrees} deg")
        self.timer = self.create_timer(0.05, self.turn_loop)
        
    def turn_loop(self):
        if self.emergency_stop:
            self.stop_robot()
            self.is_busy = False
            self.timer.cancel()
            self.get_logger().info("Turn aborted.")
            return

        delta = self.current_yaw - self.start_yaw
        # Normalize between -pi and pi
        if delta > math.pi: delta -= 2 * math.pi
        elif delta < -math.pi: delta += 2 * math.pi
        
        self.turned_so_far += abs(delta)
        self.start_yaw = self.current_yaw # Update for next tick to accumulate
        
        if self.turned_so_far >= self.target_value:
            self.stop_robot()
            self.is_busy = False
            self.timer.cancel()
            self.get_logger().info("Turn completed successfully.")
            return
            
        msg = Twist()
        msg.angular.z = self.ANGULAR_SPEED * self.direction
        self.cmd_vel_pub.publish(msg)

    def execute_track(self, offset):
        self.task_type = 'track' # Important for scan_cb
        
        if self.emergency_stop:
            self.stop_robot()
            self.get_logger().info("Cannot track, obstacle in front!")
            return
            
        # P-controller for tracking
        Kp_angular = 1.0
        Kp_linear = 0.2
        
        angular_speed = -offset * Kp_angular
        # Cap angular
        if angular_speed > self.ANGULAR_SPEED: angular_speed = self.ANGULAR_SPEED
        if angular_speed < -self.ANGULAR_SPEED: angular_speed = -self.ANGULAR_SPEED
        
        # Slow down linear if offset is large (turning in place), go faster if centered
        linear_speed = Kp_linear * (1.0 - abs(offset))
        if linear_speed < 0.0: linear_speed = 0.0
        
        msg = Twist()
        msg.linear.x = float(linear_speed)
        msg.angular.z = float(angular_speed)
        self.cmd_vel_pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = TacticalExecutorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_robot()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
