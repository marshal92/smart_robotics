#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
import subprocess
import time
import threading
import math

from nav2_msgs.srv import ClearEntireCostmap
from slam_toolbox.srv import Pause
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from smart_interfaces.msg import SmartCommand

class MissionManager(Node):
    def __init__(self):
        super().__init__('mission_manager')

        # Node parameters
        self.declare_parameter('is_simulation', True)
        self.use_sim_time = self.get_parameter('is_simulation').value
        
        # Coordinates from infrastructure (Gazebo)
        self.declare_parameter('spawn_x', 0.0)
        self.declare_parameter('spawn_y', 0.0)
        self.declare_parameter('spawn_yaw', 0.0)

        self._lock = threading.Lock()
        self.session_name = "mission_nav_session"
        self._session_cache = {'running': False, 'ts': 0.0, 'ttl': 2.0}

        # Publisher for initial pose initialization (like in RViz)
        self.init_pose_pub = self.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)

        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE
        )
        # self.sub = self.create_subscription(String, '/system_command', self.command_cb, qos)
        self.sub = self.create_subscription(SmartCommand, '/smart_command', self.command_cb, qos)

        self.get_logger().info(f"Mission Manager started. sim_time={self.use_sim_time}")

    # MANAGEMENT OF THE SESSION

    def _check_session_real(self):
        r = subprocess.run(
            ['tmux', 'has-session', '-t', self.session_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0
        )
        return r.returncode == 0

    def _invalidate_cache(self):
        self._session_cache['ts'] = 0.0

    def _start_mission(self, slam_mode="lifelong", map_name="none"):
        with self._lock:
            if self._check_session_real():
                self.get_logger().warn("Mission already running! Stop it first.")
                return
            
            sim = "true" if self.use_sim_time else "false"
            launch_file = f"bringup_{slam_mode}.launch.py"
            
            # CLEAN start of navigation (without workarounds for passing coordinates to launch)
            cmd = f"ros2 launch smart_nav {launch_file} map_name:={map_name} use_sim_time:={sim}"
            
            subprocess.Popen(
                ['tmux', 'new-session', '-d', '-s', self.session_name, cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
            )
            self._invalidate_cache()
            self.get_logger().info(f"Tactical Layer started: {slam_mode} | Map: {map_name}")

            # If we have loaded a ready map, check coordinates before firing
            if slam_mode == "lifelong":
                x = float(self.get_parameter('spawn_x').value)
                y = float(self.get_parameter('spawn_y').value)
                yaw = float(self.get_parameter('spawn_yaw').value)

                #threading.Thread(target=self._publish_initial_pose, args=(x, y, yaw), daemon=True).start()
                # CONDITION: we only fire if coordinates are not zero (more than 1 cm)
                if abs(x) > 0.01 or abs(y) > 0.01 or abs(yaw) > 0.01:
                    threading.Thread(target=self._publish_initial_pose, args=(x, y, yaw), daemon=True).start()
                else:
                    self.get_logger().info("Spawn is near (0,0,0). Skipping /initialpose to protect graph.")

    def _publish_initial_pose(self, x, y, yaw):
        """Waits for SLAM to boot and then sends the initial pose"""
        self.get_logger().info("Waiting for SLAM Toolbox to boot before sending initial pose...")
        time.sleep(6.0) # Give 6 seconds for nodes inside tmux to load
        
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = float(x)
        msg.pose.pose.position.y = float(y)
        
        # Conversion of yaw (Euler) to Quaternion
        msg.pose.pose.orientation.z = math.sin(float(yaw) / 2.0)
        msg.pose.pose.orientation.w = math.cos(float(yaw) / 2.0)
        
        # Give a small covariance (confidence in the point)
        msg.pose.covariance[0] = 0.1   # X
        msg.pose.covariance[7] = 0.1   # Y
        msg.pose.covariance[35] = 0.05 # Yaw
        
        self.init_pose_pub.publish(msg)
        self.get_logger().info(f"RViz-style Initial Pose Published: x={x}, y={y}, yaw={yaw}")

    def _stop_mission(self):
        with self._lock:
            if not self._check_session_real():
                self.get_logger().warn("No active missions.")
                return
            self.get_logger().info("Stopping tactical layer (Sending Ctrl+C)...")
            subprocess.run(
                ['tmux', 'send-keys', '-t', self.session_name, 'C-c'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        def _wait():
            for _ in range(10):
                time.sleep(1)
                if not self._check_session_real():
                    self.get_logger().info("Tactical layer cleanly shutdown.")
                    self._invalidate_cache()
                    return
            self.get_logger().error("Forceful destruction of tmux session!")
            subprocess.run(['tmux', 'kill-session', '-t', self.session_name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._invalidate_cache()

        threading.Thread(target=_wait, daemon=True).start()

    def _restart_mission(self):
        def _do():
            self._stop_mission()
            time.sleep(3)  
            self._start_mission(slam_mode="lifelong", map_name="new_213_map")
        threading.Thread(target=_do, daemon=True).start()

    # Native freeride handled by start_mission("mapping", "none")

    # NATIVE CALLS TO ROS 2

    def _native_clear_costmap(self, service_name):
        client = self.create_client(ClearEntireCostmap, service_name)
        if client.wait_for_service(timeout_sec=2.0):
            client.call_async(ClearEntireCostmap.Request())
            self.get_logger().info(f"Cleared: {service_name}")

    def _native_set_radiation(self, is_active):
        client = self.create_client(SetParameters, '/radiation_field_server/set_parameters')
        if client.wait_for_service(timeout_sec=2.0):
            req = SetParameters.Request()
            param = Parameter(name='is_active', value=ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=is_active))
            req.parameters.append(param)
            client.call_async(req)
            self.get_logger().info(f"Radiation server set to: {'ON' if is_active else 'OFF'}")

    def _native_toggle_slam(self):
        client = self.create_client(Pause, '/slam_toolbox/pause_new_measurements')
        if client.wait_for_service(timeout_sec=2.0):
            client.call_async(Pause.Request())
            self.get_logger().info("SLAM Toolbox toggled")

    def _native_save_map(self, map_name):
        map_path = f"/home/oleksandr/ros2_ws/src/smart_robotics/smart_nav/maps/{map_name}"
        self.get_logger().info(f"Saving SLAM map to {map_path}...")
        
        # Save Pose Graph (For Lifelong SLAM)
        cmd_pg = [
            'ros2', 'service', 'call', '/slam_toolbox/serialize_map', 
            'slam_toolbox/srv/SerializePoseGraph', f"{{filename: '{map_path}'}}"
        ]
        subprocess.run(cmd_pg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Save 2D Grid (For Nav2 / RViz)
        cmd_2d = ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', map_path]
        subprocess.run(cmd_2d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        self.get_logger().info(f"Map {map_name} saved successfully!")

    # COMMAND DISPATCHER
    def command_cb(self, msg):
        # Ignore everything that is not addressed to the system
        if msg.target_system != 'system':
            return

        cmd = msg.command.strip().lower()
        self.get_logger().info(f"Received system action: '{cmd}'")

        legacy_dispatch = {
            'start_213':          lambda: threading.Thread(target=self._start_mission, args=("lifelong", "213_map"), daemon=True).start(),
            'start_shelter_zero': lambda: threading.Thread(target=self._start_mission, args=("lifelong", "shelter_zero"), daemon=True).start(),
            'start_shelter':      lambda: threading.Thread(target=self._start_mission, args=("lifelong", "shelter_map"), daemon=True).start(),
            'start_kitchen':      lambda: threading.Thread(target=self._start_mission, args=("lifelong", "kitchen_map"), daemon=True).start(),
            'start_mapping':      lambda: threading.Thread(target=self._start_mission, args=("mapping", "none"), daemon=True).start(),
            'stop':               lambda: threading.Thread(target=self._stop_mission, daemon=True).start(),
            'restart':            lambda: self._restart_mission(),
            'start_freeride':     lambda: threading.Thread(target=self._start_mission, args=("mapping", "none"), daemon=True).start(),
            'clear_costmaps':     lambda: [self._native_clear_costmap('/local_costmap/clear_entirely_local_costmap'), 
                                           self._native_clear_costmap('/global_costmap/clear_entirely_global_costmap')],
            'rad_on':             lambda: self._native_set_radiation(True),
            'rad_off':            lambda: self._native_set_radiation(False),
            'toggle_slam':        lambda: self._native_toggle_slam()
        }

        if cmd in legacy_dispatch:
            legacy_dispatch[cmd]()
            return

        # NEW UNIVERSAL SYNTAX
        cmd_parts = cmd.split(':')
        action = cmd_parts[0]

        if action == 'start':
            mode = cmd_parts[1] if len(cmd_parts) > 1 else "lifelong"
            map_name = cmd_parts[2] if len(cmd_parts) > 2 else "none"
            threading.Thread(target=self._start_mission, args=(mode, map_name), daemon=True).start()
        elif action == 'save_map':
            map_name = cmd_parts[1] if len(cmd_parts) > 1 else "new_map"
            threading.Thread(target=self._native_save_map, args=(map_name,), daemon=True).start()
        else:
            self.get_logger().error(f"Unknown system command: '{cmd}'")

def main(args=None):
    rclpy.init(args=args)
    node = MissionManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node._stop_mission()
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()