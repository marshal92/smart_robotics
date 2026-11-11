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
        self.arm_session_name = "arm_session"

        # Subscribe to the unified command bus
        self.sub = self.create_subscription(SmartCommand, '/smart_command', self.command_cb, 10)

        # Forward Shadow commands over a local server topic (no bridge needed)
        self.shadow_pub = self.create_publisher(String, '/shadow_command', 10)
        self.shadow_param_cli = self.create_client(SetParameters, '/shadow_teleop/set_parameters')

        self.get_logger().info(
            f"[Server] Twin Orchestrator started (sim_mode={self.worker_use_sim_time})! "
            "Waiting for /smart_command..."
        )

    def _check_arm_session(self) -> bool:
        try:
            active_nodes = self.get_node_names()
            if 'control_hub' in active_nodes or 'tactical_server' in active_nodes:
                return True
        except Exception:
            pass

        r = subprocess.run(
            ['tmux', 'has-session', '-t', self.arm_session_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0
        )
        return r.returncode == 0

    def _start_arm_backend(self, use_rviz: bool = False):
        with self._lock:
            if self._check_arm_session():
                self.get_logger().info("[Server] Arm backend is already running.")
                return

            sim_str = "true" if self.worker_use_sim_time else "false"
            rviz_str = "true" if use_rviz else "false"
            cmd = (
                f"source /opt/ros/jazzy/setup.bash && "
                f"source ~/ros2_ws/install/setup.bash && "
                f"ros2 launch smart_server arm_backend.launch.py "
                f"use_sim_time:={sim_str} use_arm:=true use_rviz:={rviz_str}"
            )
            subprocess.Popen(
                ['tmux', 'new-session', '-d', '-s', self.arm_session_name, f"bash -c '{cmd}'"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
            )
            self.get_logger().info(
                f"[Server] Arm backend started in tmux session '{self.arm_session_name}' "
                f"(use_sim_time={sim_str}, use_rviz={rviz_str})."
            )

    def _stop_arm_backend(self):
        with self._lock:
            r = subprocess.run(
                ['tmux', 'has-session', '-t', self.arm_session_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0
            )
            if r.returncode != 0:
                self.get_logger().info("[Server] Arm backend session is not running.")
                return

            subprocess.run(
                ['tmux', 'send-keys', '-t', self.arm_session_name, 'C-c'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            subprocess.run(
                ['tmux', 'kill-session', '-t', self.arm_session_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self.get_logger().info(f"[Server] Arm backend session '{self.arm_session_name}' stopped.")

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
            elif cmd == 'arm_on':
                threading.Thread(target=self._start_arm_backend, args=(False,), daemon=True).start()
                return
            elif cmd == 'arm_on_rviz':
                threading.Thread(target=self._start_arm_backend, args=(True,), daemon=True).start()
                return
            elif cmd in ('arm_off', 'stop'):
                if cmd == 'arm_off':
                    threading.Thread(target=self._stop_arm_backend, daemon=True).start()
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
