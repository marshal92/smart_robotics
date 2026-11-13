#!/usr/bin/env python3
import subprocess
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from smart_interfaces.msg import SmartCommand
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue


class TwinOrchestrator(Node):
    def __init__(self):
        super().__init__('twin_orchestrator')

        self.declare_parameter('worker_use_sim_time', False)
        self.worker_use_sim_time = self.get_parameter('worker_use_sim_time').value

        self._lock = threading.Lock()
        self.arm_moveit_session = "arm_moveit_session"
        self.arm_servo_session = "arm_servo_session"

        # Subscribe to the unified command bus
        self.sub = self.create_subscription(SmartCommand, '/smart_command', self.command_cb, 10)

        # Forward Shadow commands over a local server topic (no bridge needed)
        self.shadow_pub = self.create_publisher(String, '/shadow_command', 10)
        self.shadow_param_cli = self.create_client(SetParameters, '/shadow_teleop/set_parameters')

        self.get_logger().info(
            f"[Server] Twin Orchestrator started (sim_mode={self.worker_use_sim_time})! "
            "Waiting for /smart_command..."
        )

    def _is_session_active(self, session_name: str, expected_nodes: tuple) -> bool:
        try:
            active_nodes = self.get_node_names()
            if any(node in active_nodes for node in expected_nodes):
                return True
        except Exception:
            pass

        r = subprocess.run(
            ['tmux', 'has-session', '-t', session_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0
        )
        return r.returncode == 0

    def _start_arm_session(self, session_name: str, launch_file: str, expected_nodes: tuple):
        with self._lock:
            if self._is_session_active(session_name, expected_nodes):
                self.get_logger().info(f"[Server] Session '{session_name}' is already running.")
                return

            sim_str = "true" if self.worker_use_sim_time else "false"
            cmd = (
                f"source /opt/ros/jazzy/setup.bash && "
                f"source ~/ros2_ws/install/setup.bash && "
                f"ros2 launch smart_server {launch_file} use_sim_time:={sim_str}"
            )
            subprocess.Popen(
                ['tmux', 'new-session', '-d', '-s', session_name, f"bash -c '{cmd}'"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
            )
            self.get_logger().info(
                f"[Server] Started '{launch_file}' in tmux session '{session_name}' "
                f"(use_sim_time={sim_str})."
            )

    def _stop_arm_session(self, session_name: str):
        with self._lock:
            self._kill_tmux_session(session_name)

    def _stop_all_arm_sessions(self):
        with self._lock:
            for name in (self.arm_moveit_session, self.arm_servo_session, "arm_session"):
                self._kill_tmux_session(name)

    def _kill_tmux_session(self, session_name: str):
        r = subprocess.run(
            ['tmux', 'has-session', '-t', session_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0
        )
        if r.returncode != 0:
            return

        subprocess.run(
            ['tmux', 'send-keys', '-t', session_name, 'C-c'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1.0)
        subprocess.run(
            ['tmux', 'kill-session', '-t', session_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.get_logger().info(f"[Server] Stopped tmux session '{session_name}'.")

    def _set_shadow_active(self, is_active: bool):
        if self.shadow_param_cli.wait_for_service(timeout_sec=1.0):
            req = SetParameters.Request()
            param = Parameter(
                name='is_active',
                value=ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=is_active)
            )
            req.parameters.append(param)
            self.shadow_param_cli.call_async(req)
            self.get_logger().info(f"[Server] Shadow Teleop set to: {'ON' if is_active else 'OFF'}")

    def command_cb(self, msg):
        cmd = msg.command.strip().lower()

        if msg.target_system == 'system':
            if cmd in ('shadow_on', 'shadow_off'):
                self._set_shadow_active(cmd == 'shadow_on')
                return
            elif cmd == 'arm_moveit_on':
                threading.Thread(
                    target=self._start_arm_session,
                    args=(self.arm_moveit_session, 'arm_moveit.launch.py', ('control_hub', 'tactical_server', 'move_group')),
                    daemon=True,
                ).start()
                return
            elif cmd == 'arm_moveit_off':
                threading.Thread(
                    target=self._stop_arm_session,
                    args=(self.arm_moveit_session,),
                    daemon=True,
                ).start()
                return
            elif cmd == 'arm_servo_on':
                threading.Thread(
                    target=self._start_arm_session,
                    args=(self.arm_servo_session, 'arm_servo.launch.py', ('teleop_manager', 'servo_node')),
                    daemon=True,
                ).start()
                return
            elif cmd == 'arm_servo_off':
                threading.Thread(
                    target=self._stop_arm_session,
                    args=(self.arm_servo_session,),
                    daemon=True,
                ).start()
                return
            elif cmd == 'arm_off':
                threading.Thread(target=self._stop_all_arm_sessions, daemon=True).start()
                return
            elif cmd == 'stop':
                return

        # Handle operator/shadow commands only
        if msg.target_system != 'operator':
            return

        if cmd == 'execute':
            self.get_logger().info("[Server] EXECUTE command. Dispatching Shadow route...")
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
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
