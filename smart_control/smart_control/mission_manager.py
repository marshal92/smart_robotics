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
import json

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
        self.rad_session_name = "radiation_session"
        self._session_cache = {'running': False, 'ts': 0.0, 'ttl': 2.0}

        # Radiation subsystem process lifecycle state (no internal sensor/map logic here)
        self.rad_starting = False
        self.rad_ready = False

        # Publisher for initial pose initialization (like in RViz)
        self.init_pose_pub = self.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)

        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE
        )
        self.sub = self.create_subscription(SmartCommand, '/smart_command', self.command_cb, qos)
        self.cmd_pub = self.create_publisher(SmartCommand, '/smart_command', 10)

        status_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL
        )
        self.rad_status_pub = self.create_publisher(String, '/radiation/status', status_qos)
        self.rad_status_sub = self.create_subscription(String, '/radiation/status', self._rad_status_cb, status_qos)

        if not self._check_rad_session_real():
            self._publish_rad_lifecycle_status("NOT_RUNNING", "init", "ok", "")

        self.get_logger().info(f"Mission Manager started. sim_time={self.use_sim_time}")

    # HELPER TO BUILD ROBUST SHELL COMMAND FOR TMUX
    def _build_tmux_ros_cmd(self, cmd: str) -> str:
        return (
            "source /opt/ros/jazzy/setup.bash && "
            "source ~/ros2_ws/install/setup.bash && "
            "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && "
            "[ -f /home/oleksandr/cyclonedds.xml ] && export CYCLONEDDS_URI=file:///home/oleksandr/cyclonedds.xml; "
            f"exec {cmd}"
        )

    # RADIATION SUBSYSTEM PROCESS LIFECYCLE

    def _check_rad_session_real(self):
        # Also check if radiation nodes are already alive in ROS graph (e.g. started by asym launch or existing session)
        try:
            active_nodes = self.get_node_names()
            if 'radiation_manager' in active_nodes or 'radiation_field_server' in active_nodes:
                self.rad_ready = True
                self.rad_starting = False
                return True
        except Exception:
            pass

        r = subprocess.run(
            ['tmux', 'has-session', '-t', self.rad_session_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0
        )
        return r.returncode == 0

    def _publish_rad_lifecycle_status(self, state: str, last_command: str, last_result: str, error: str = ""):
        payload = {
            "ready": False,
            "state": state,
            "working_map": "",
            "recording": False,
            "field_active": False,
            "last_command": last_command,
            "last_result": last_result,
            "error": error
        }
        msg = String()
        msg.data = json.dumps(payload)
        self.rad_status_pub.publish(msg)

    def _rad_status_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
            if data.get("ready", False):
                self.rad_ready = True
                self.rad_starting = False
        except Exception:
            pass

    def _start_radiation(self, initial_active=False, trigger_cmd="rad_start"):
        with self._lock:
            if self._check_rad_session_real():
                if not self.rad_ready:
                    self.get_logger().info("Radiation subsystem is currently starting up. Ignoring duplicate start.")
                else:
                    self.get_logger().info("Radiation subsystem is already running.")
                return
            if self.rad_starting:
                self.get_logger().info("Radiation subsystem launch already in progress.")
                return

            self.rad_starting = True
            self.rad_ready = False
            self._publish_rad_lifecycle_status("STARTING", trigger_cmd, "starting", "")

            sim = "true" if self.use_sim_time else "false"
            act = "true" if initial_active else "false"
            cmd = (
                f"ros2 launch smart_radiation radiation_bringup.launch.py "
                f"use_sim_time:={sim} initial_active:={act}"
            )
            env_cmd = self._build_tmux_ros_cmd(cmd)

            subprocess.Popen(
                ['tmux', 'new-session', '-d', '-s', self.rad_session_name, env_cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
            )
            self.get_logger().info(f"Radiation subsystem bringup started (initial_active={act}).")

    def _stop_radiation_session(self):
        with self._lock:
            if not self._check_rad_session_real():
                return
            subprocess.run(
                ['tmux', 'send-keys', '-t', self.rad_session_name, 'C-c'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            if self._check_rad_session_real():
                subprocess.run(
                    ['tmux', 'kill-session', '-t', self.rad_session_name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            self.rad_ready = False
            self.rad_starting = False

    # MANAGEMENT OF THE NAVIGATION SESSION

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

            # CLEAN start of navigation
            cmd = f"ros2 launch smart_nav {launch_file} map_name:={map_name} use_sim_time:={sim}"
            env_cmd = self._build_tmux_ros_cmd(cmd)

            subprocess.Popen(
                ['tmux', 'new-session', '-d', '-s', self.session_name, env_cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
            )
            self._invalidate_cache()
            self.get_logger().info(f"Tactical Layer started: {slam_mode} | Map: {map_name}")

            # Note: automatic /initialpose on start disabled per user instruction to protect map/graph
            self.get_logger().info("Automatic /initialpose on mission start is disabled.")

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

    # NATIVE CALLS TO ROS 2

    def _native_clear_costmap(self, service_name):
        client = self.create_client(ClearEntireCostmap, service_name)
        if client.wait_for_service(timeout_sec=2.0):
            client.call_async(ClearEntireCostmap.Request())
            self.get_logger().info(f"Cleared: {service_name}")

    def _native_set_shadow(self, is_active):
        client_shadow = self.create_client(SetParameters, '/shadow_teleop/set_parameters')
        if client_shadow.wait_for_service(timeout_sec=2.0):
            req = SetParameters.Request()
            param = Parameter(name='is_active', value=ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=is_active))
            req.parameters.append(param)
            client_shadow.call_async(req)
        self.get_logger().info(f"Shadow Teleop set to: {'ON' if is_active else 'OFF'}")

    def _native_set_max_speed(self, speed_val: float):
        client_ctrl = self.create_client(SetParameters, '/controller_server/set_parameters')
        if client_ctrl.wait_for_service(timeout_sec=2.0):
            req = SetParameters.Request()
            param = Parameter(
                name='FollowPath.vx_max',
                value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE, double_value=float(speed_val))
            )
            req.parameters.append(param)
            client_ctrl.call_async(req)
            self.get_logger().info(f"Updated Nav2 FollowPath.vx_max to: {speed_val:.2f} m/s")
        else:
            self.get_logger().warn("Could not set speed: /controller_server/set_parameters not available")

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

        # If radiation subsystem is active, request save via public command
        if self._check_rad_session_real() and self.rad_ready:
            rad_cmd = SmartCommand()
            rad_cmd.target_system = 'radiation'
            rad_cmd.command = 'rad_save'
            self.cmd_pub.publish(rad_cmd)

    # COMMAND DISPATCHER
    def command_cb(self, msg):
        if msg.target_system != 'system':
            return

        cmd = msg.command.strip().lower()
        cmd_parts = cmd.split(':')
        action = cmd_parts[0]

        # Handle radiation subsystem lifecycle and guard unstarted radiation commands
        if action == 'rad_start':
            self.get_logger().info("Received 'rad_start': launching radiation subsystem...")
            threading.Thread(target=self._start_radiation, args=(False, cmd), daemon=True).start()
            return

        if action == 'rad_on':
            if not self._check_rad_session_real():
                self.get_logger().info("Radiation subsystem not running. Launching radiation_bringup with field ON...")
                threading.Thread(target=self._start_radiation, args=(True, cmd), daemon=True).start()
                return
            if not self.rad_ready:
                self.get_logger().warn("Radiation subsystem is still starting up. Please wait...")
                self._publish_rad_lifecycle_status("STARTING", cmd, "error", "Radiation subsystem is still starting")
                return
            # Already running and ready -> radiation_manager handles rad_on directly
            return

        if action in ('rad_off', 'rad_geiger_on', 'rad_geiger_off', 'rad_load', 'rad_source', 'rad_record', 'rad_save', 'rad_stop', 'rad_clear'):
            if not self._check_rad_session_real():
                err_msg = f"Radiation subsystem is not running. Cannot execute '{cmd}'. Send 'rad_on' or 'rad_start' first."
                self.get_logger().warn(err_msg)
                self._publish_rad_lifecycle_status("NOT_RUNNING", cmd, "error", err_msg)
                return
            if not self.rad_ready:
                err_msg = f"Radiation subsystem is still starting. Cannot execute '{cmd}' yet."
                self.get_logger().warn(err_msg)
                self._publish_rad_lifecycle_status("STARTING", cmd, "error", err_msg)
                return
            # Running and ready -> radiation_manager handles these commands directly
            return

        self.get_logger().info(f"Received system action: '{cmd}'")

        legacy_dispatch = {
            'start_213':          lambda: threading.Thread(target=self._start_mission, args=("lifelong", "213_map"), daemon=True).start(),
            'start_shelter_zero': lambda: threading.Thread(target=self._start_mission, args=("lifelong", "shelter_012.7"), daemon=True).start(),
            'start_shelter':      lambda: threading.Thread(target=self._start_mission, args=("lifelong", "shelter_map"), daemon=True).start(),
            'start_kitchen':      lambda: threading.Thread(target=self._start_mission, args=("lifelong", "kitchen_map"), daemon=True).start(),
            'start_mapping':      lambda: threading.Thread(target=self._start_mission, args=("mapping", "none"), daemon=True).start(),
            'stop':               lambda: threading.Thread(target=self._stop_mission, daemon=True).start(),
            'restart':            lambda: self._restart_mission(),
            'start_freeride':     lambda: threading.Thread(target=self._start_mission, args=("mapping", "none"), daemon=True).start(),
            'clear_costmaps':     lambda: [self._native_clear_costmap('/local_costmap/clear_entirely_local_costmap'),
                                           self._native_clear_costmap('/global_costmap/clear_entirely_global_costmap')],
            'shadow_on':          lambda: self._native_set_shadow(True),
            'shadow_off':         lambda: self._native_set_shadow(False),
            'toggle_slam':        lambda: self._native_toggle_slam()
        }

        if cmd in legacy_dispatch:
            legacy_dispatch[cmd]()
            return

        if action == 'start':
            mode = cmd_parts[1] if len(cmd_parts) > 1 else "lifelong"
            map_name = cmd_parts[2] if len(cmd_parts) > 2 else "none"
            threading.Thread(target=self._start_mission, args=(mode, map_name), daemon=True).start()
        elif action == 'save_map':
            map_name = cmd_parts[1] if len(cmd_parts) > 1 else "new_map"
            threading.Thread(target=self._native_save_map, args=(map_name,), daemon=True).start()
        elif action == 'set_speed':
            try:
                speed_val = float(cmd_parts[1]) if len(cmd_parts) > 1 else 0.8
                threading.Thread(target=self._native_set_max_speed, args=(speed_val,), daemon=True).start()
            except ValueError:
                self.get_logger().error(f"Invalid speed value in command: '{cmd}'")
        else:
            self.get_logger().error(f"Unknown system command: '{cmd}'")


def main(args=None):
    rclpy.init(args=args)
    node = MissionManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node._stop_mission()
        node._stop_radiation_session()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
