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
        self.status_pub = self.create_publisher(String, '/tactical/status', 10)
        
        # Idle state: ONLY listen to /smart_command. No timers, no /odom, no /scan.
        self.create_subscription(SmartCommand, '/smart_command', self.cmd_cb, 10)
        self.odom_sub = None
        self.scan_sub = None
        self.timer = None
        self.track_watchdog_timer = None
        
        # State
        self.is_busy = False
        self.emergency_stop = False
        self.task_type = None  # 'move', 'turn', or 'track'
        self.current_status = None
        self.target_value = 0.0
        self.start_x = 0.0
        self.start_y = 0.0
        self.start_yaw = 0.0
        self.start_pose_captured = False
        self.direction = 1.0  # 1.0 forward, -1.0 backward
        self.task_start_time = 0.0
        self.task_timeout = 0.0
        
        # Odometry cache
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_yaw = 0.0
        self.odom_ready = False
        
        # Precomputed scan beam indices for +/- 20 deg front cone
        self.cached_cone_config = None
        self.cached_cone_indices = None
        
        # Control parameters
        self.MAX_LINEAR = 0.3
        self.MIN_LINEAR = 0.1
        self.ANGULAR_SPEED = 0.5
        self.SAFETY_DIST = 0.5

        self.publish_status("IDLE")
        self.get_logger().info("Tactical Executor Node ready (Zero-idle resource mode). Waiting for /smart_command.")

    def publish_status(self, status_str: str):
        if status_str != self.current_status:
            self.current_status = status_str
            msg = String()
            msg.data = status_str
            self.status_pub.publish(msg)

    def _cancel_timer(self):
        if self.timer is not None:
            self.timer.cancel()
            self.destroy_timer(self.timer)
            self.timer = None

    def _cancel_track_watchdog(self):
        if self.track_watchdog_timer is not None:
            self.track_watchdog_timer.cancel()
            self.destroy_timer(self.track_watchdog_timer)
            self.track_watchdog_timer = None

    def _enable_odom_sub(self):
        self.odom_ready = False
        if self.odom_sub is None:
            self.odom_sub = self.create_subscription(Odometry, '/odom', self.odom_cb, 10)

    def _disable_odom_sub(self):
        if self.odom_sub is not None:
            self.destroy_subscription(self.odom_sub)
            self.odom_sub = None
        self.odom_ready = False

    def _enable_scan_sub(self):
        if self.scan_sub is None:
            self.scan_sub = self.create_subscription(LaserScan, '/scan', self.scan_cb, 10)

    def _disable_scan_sub(self):
        if self.scan_sub is not None:
            self.destroy_subscription(self.scan_sub)
            self.scan_sub = None

    def stop_robot(self):
        """Immediately stop movement and destroy all active timers & dynamic subs."""
        self._cancel_timer()
        self._cancel_track_watchdog()
        self._disable_scan_sub()
        self._disable_odom_sub()
        zero_twist = Twist()
        self.cmd_vel_pub.publish(zero_twist)

    def abort_task(self, reason="Aborted"):
        self.stop_robot()
        self.is_busy = False
        self.task_type = None
        self.publish_status("IDLE")
        self.get_logger().info(f"Tactical task finished/aborted: {reason}")

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
        if self.emergency_stop:
            return
        if not self.is_busy and self.task_type != 'track':
            return
        if self.task_type == 'move' and self.direction < 0:
            return
            
        num_ranges = len(msg.ranges)
        if num_ranges < 10:
            return
        
        # Precompute cone indices once to avoid expensive trig in Python every frame
        config_key = (num_ranges, round(msg.angle_min, 4), round(msg.angle_increment, 6))
        if self.cached_cone_config != config_key or self.cached_cone_indices is None:
            self.cached_cone_config = config_key
            cone_rad = math.radians(20.0)
            indices = []
            for i in range(num_ranges):
                ang = msg.angle_min + i * msg.angle_increment
                ang = math.atan2(math.sin(ang), math.cos(ang))  # Normalize to [-pi, pi]
                if abs(ang) < cone_rad:
                    indices.append(i)
            self.cached_cone_indices = indices

        # Fast scan over precomputed indices only
        for i in self.cached_cone_indices:
            r = msg.ranges[i]
            if 0.02 < r < self.SAFETY_DIST:
                self.get_logger().warn(f"OBSTACLE DETECTED at {r:.2f}m! Immediate Emergency Stop.")
                self.emergency_stop = True
                self.stop_robot()
                self.is_busy = False
                self.task_type = None
                self.publish_status("OBSTACLE_STOP")
                break

    def cmd_cb(self, msg):
        target = msg.target_system.strip().lower()
        command = msg.command.strip().lower()

        # Global or navigation stop/cancel commands must also abort active tactical motion
        if (target == 'system' and command in ('stop', 'start_freeride', 'restart')) or \
           (target == 'nav' and command in ('cancel', 'rth')):
            if self.is_busy or self.task_type is not None:
                self.get_logger().info(f"Received '{target}:{command}'. Aborting active tactical execution.")
                self.abort_task(reason=f"Interrupted by '{target}:{command}'")
            return

        if target != 'tactical':
            return

        # Always process stop/cancel/abort even if is_busy is True
        if command in ('stop', 'cancel', 'abort'):
            self.get_logger().info(f"Received '{command}' command. Aborting tactical execution.")
            self.abort_task(reason=f"Cancelled by '{command}'")
            return

        if self.is_busy:
            self.get_logger().warn(f"Busy executing tactical task ({self.task_type}). Ignoring new request: '{command}'")
            return

        payload = {}
        if msg.payload_json:
            try:
                payload = json.loads(msg.payload_json)
            except Exception as e:
                self.get_logger().error(f"JSON Parse error in tactical command '{command}': {e}")
                return
            if not isinstance(payload, dict):
                self.get_logger().error(f"Expected JSON object in tactical command '{command}', got {type(payload).__name__}")
                return

        if command == 'move_relative':
            try:
                dist = float(payload.get('distance', 1.0))
            except (ValueError, TypeError) as e:
                self.get_logger().error(f"Invalid 'distance' in move_relative: {e}")
                return
            if not math.isfinite(dist) or abs(dist) <= 0.0:
                self.get_logger().error(f"Non-finite or zero distance in move_relative: {dist}")
                return
            direction = str(payload.get('direction', 'forward')).strip().lower()
            self.execute_move(dist, direction)
            
        elif command == 'turn_relative':
            try:
                deg = float(payload.get('degrees', 90.0))
            except (ValueError, TypeError) as e:
                self.get_logger().error(f"Invalid 'degrees' in turn_relative: {e}")
                return
            if not math.isfinite(deg) or abs(deg) <= 0.0:
                self.get_logger().error(f"Non-finite or zero degrees in turn_relative: {deg}")
                return
            self.execute_turn(deg)
            
        elif command == 'track_target':
            try:
                offset = float(payload.get('offset', 0.0))
            except (ValueError, TypeError) as e:
                self.get_logger().error(f"Invalid 'offset' in track_target: {e}")
                return
            if not math.isfinite(offset):
                self.get_logger().error("Non-finite offset in track_target")
                return
            self.execute_track(offset)
        else:
            self.get_logger().warn(f"Unknown tactical command: '{command}'")

    def execute_move(self, distance, direction_str):
        self.stop_robot()
        self._enable_odom_sub()
        self.is_busy = True
        self.emergency_stop = False
        self.start_pose_captured = False
        self.task_type = 'move'
        self.target_value = abs(distance)
        self.direction = 1.0 if direction_str == 'forward' else -1.0
        if self.direction > 0:
            self._enable_scan_sub()
        
        self.task_start_time = time.time()
        # Safety timeout: expected time + 5.0 seconds
        self.task_timeout = max(5.0, (self.target_value / self.MIN_LINEAR) + 5.0)
        
        self.publish_status("MOVING")
        self.get_logger().info(f"Starting tactical move: {distance}m {direction_str} (timeout: {self.task_timeout:.1f}s)")
        self.timer = self.create_timer(0.05, self.move_loop)
        
    def move_loop(self):
        if self.emergency_stop:
            return

        # Check safety timeout to prevent infinite CPU burn if odom or wheels hang
        if (time.time() - self.task_start_time) > self.task_timeout:
            self.get_logger().warn("Move execution timeout! Stopping to save resources.")
            self.abort_task("Move timeout")
            return

        if not self.odom_ready:
            return
        if not self.start_pose_captured:
            self.start_x = self.current_x
            self.start_y = self.current_y
            self.start_pose_captured = True

        dx = self.current_x - self.start_x
        dy = self.current_y - self.start_y
        dist_moved = math.hypot(dx, dy)
        remaining = self.target_value - dist_moved
        
        if remaining <= 0.05:
            self.abort_task("Move completed successfully")
            return
            
        speed = (remaining / 0.5) * self.MAX_LINEAR if remaining < 0.5 else self.MAX_LINEAR
        speed = max(speed, self.MIN_LINEAR)
        
        msg = Twist()
        msg.linear.x = speed * self.direction
        self.cmd_vel_pub.publish(msg)

    def execute_turn(self, degrees):
        self.stop_robot()
        self._enable_odom_sub()
        self.is_busy = True
        self.emergency_stop = False
        self.start_pose_captured = False
        self.task_type = 'turn'
        self.target_value = math.radians(abs(degrees))
        self.direction = 1.0 if degrees > 0 else -1.0
        self.turned_so_far = 0.0
        
        self.task_start_time = time.time()
        # Safety timeout: expected time + 5.0 seconds
        self.task_timeout = max(5.0, (self.target_value / self.ANGULAR_SPEED) + 5.0)
        
        self.publish_status("TURNING")
        self.get_logger().info(f"Starting tactical turn: {degrees} deg (timeout: {self.task_timeout:.1f}s)")
        self.timer = self.create_timer(0.05, self.turn_loop)
        
    def turn_loop(self):
        if self.emergency_stop:
            return

        # Safety timeout check
        if (time.time() - self.task_start_time) > self.task_timeout:
            self.get_logger().warn("Turn execution timeout! Stopping to save resources.")
            self.abort_task("Turn timeout")
            return

        if not self.odom_ready:
            return
        if not self.start_pose_captured:
            self.start_yaw = self.current_yaw
            self.start_pose_captured = True
            return

        delta = self.current_yaw - self.start_yaw
        # Normalize between -pi and pi
        if delta > math.pi: delta -= 2 * math.pi
        elif delta < -math.pi: delta += 2 * math.pi
        
        self.turned_so_far += abs(delta)
        self.start_yaw = self.current_yaw # Update for next tick to accumulate
        
        if self.turned_so_far >= self.target_value:
            self.abort_task("Turn completed successfully")
            return
            
        msg = Twist()
        msg.angular.z = self.ANGULAR_SPEED * self.direction
        self.cmd_vel_pub.publish(msg)

    def execute_track(self, offset):
        self._cancel_timer()
        self.task_type = 'track'
        self.emergency_stop = False
        self._enable_scan_sub()
        
        self.publish_status("TRACKING")
        
        # Reset 0.5s watchdog timer: if no new track command arrives, stop & release scan
        self._cancel_track_watchdog()
        self.track_watchdog_timer = self.create_timer(0.5, self._track_watchdog_cb)
        
        # P-controller for tracking
        Kp_angular = 1.0
        Kp_linear = 0.2
        
        angular_speed = -offset * Kp_angular
        if angular_speed > self.ANGULAR_SPEED: angular_speed = self.ANGULAR_SPEED
        if angular_speed < -self.ANGULAR_SPEED: angular_speed = -self.ANGULAR_SPEED
        
        linear_speed = Kp_linear * (1.0 - abs(offset))
        if linear_speed < 0.0: linear_speed = 0.0
        
        msg = Twist()
        msg.linear.x = float(linear_speed)
        msg.angular.z = float(angular_speed)
        self.cmd_vel_pub.publish(msg)

    def _track_watchdog_cb(self):
        """Called if tracking stream stops (e.g. target lost). Stops robot and destroys scan subscription."""
        self.get_logger().info("Tracking target stream lost or ended. Returning to IDLE.")
        self.abort_task("Track stream ended")

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
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
