#!/usr/bin/env python3
import os
import json
import time
import threading
from pathlib import Path
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from smart_interfaces.msg import SmartCommand
from ament_index_python.packages import get_package_share_directory


def default_maps_dir():
    env_dir = os.environ.get('SMART_RADIATION_MAPS_DIR', '').strip()
    if env_dir:
        return os.path.expanduser(env_dir)
    pkg_maps = Path(__file__).resolve().parent.parent / 'maps'
    if pkg_maps.exists():
        return str(pkg_maps)
    try:
        return os.path.join(get_package_share_directory('smart_radiation'), 'maps')
    except Exception:
        return str(pkg_maps)


def resolve_map_path(maps_dir, map_path):
    path = Path(map_path).expanduser()
    if not path.is_absolute():
        base = Path(maps_dir).expanduser() if maps_dir else Path(default_maps_dir())
        path = base / path
    if path.suffix != '.npy':
        path = Path(str(path) + '.npy')
    return str(path)


class RadiationManager(Node):
    SHM_LIVE_MAP = "/dev/shm/live_rad_map.npy"

    def __init__(self):
        super().__init__('radiation_manager')

        self.declare_parameter('maps_dir', default_maps_dir())
        self.declare_parameter('map_path', 'explored_map.npy')
        self.declare_parameter('use_virtual_geiger', True)
        self.declare_parameter('initial_active', False)

        self.maps_dir = self.get_parameter('maps_dir').value or default_maps_dir()
        os.makedirs(self.maps_dir, exist_ok=True)

        init_map = self.get_parameter('map_path').value or 'explored_map.npy'
        if not init_map.endswith('.npy'):
            init_map += '.npy'
        self.working_map = init_map
        self.use_virtual_geiger = bool(self.get_parameter('use_virtual_geiger').value)
        self.initial_active = bool(self.get_parameter('initial_active').value)

        # Subsystem state
        self.ready = False
        self.recording = False
        self.field_active = False
        self.geiger_active = False
        self.sensor_map_locked = False
        self.last_command = "init"
        self.last_result = "starting"
        self.last_error = ""

        self._cmd_lock = threading.Lock()

        # Service clients for internal radiation nodes
        self.client_mapper_params = self.create_client(SetParameters, '/radiation_mapper/set_parameters')
        self.client_server_params = self.create_client(SetParameters, '/radiation_field_server/set_parameters')
        self.client_geiger_params = self.create_client(SetParameters, '/virtual_geiger/set_parameters')
        self.client_mapper_save = self.create_client(Trigger, '/radiation_mapper/save_map')
        self.client_mapper_clear = self.create_client(Trigger, '/radiation_mapper/clear_map')

        # Status publisher (Transient Local so late subscribers immediately get latest status)
        status_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL
        )
        self.status_pub = self.create_publisher(String, '/radiation/status', status_qos)

        # Command subscriber (matching mission_manager & web UI QoS)
        cmd_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE
        )
        self.cmd_sub = self.create_subscription(SmartCommand, '/smart_command', self.command_cb, cmd_qos)

        self._publish_status()
        self.get_logger().info(
            f"Radiation Manager started (maps_dir={self.maps_dir}, map={self.working_map}, "
            f"use_virtual_geiger={self.use_virtual_geiger}, initial_active={self.initial_active})"
        )

        # Wait for internal radiation nodes in background thread
        threading.Thread(target=self._wait_and_initialize, daemon=True).start()

    def _publish_status(self, last_command=None, last_result=None, error=None):
        if last_command is not None:
            self.last_command = last_command
        if last_result is not None:
            self.last_result = last_result
        if error is not None:
            self.last_error = error

        payload = {
            "ready": self.ready,
            "state": "READY" if self.ready else "STARTING",
            "working_map": self.working_map,
            "recording": self.recording,
            "field_active": self.field_active,
            "geiger_active": self.geiger_active,
            "use_virtual_geiger": self.use_virtual_geiger,
            "last_command": self.last_command,
            "last_result": self.last_result,
            "error": self.last_error
        }
        msg = String()
        msg.data = json.dumps(payload)
        self.status_pub.publish(msg)

    def _call_service_sync(self, client, request, timeout_sec=3.0):
        if not client.wait_for_service(timeout_sec=timeout_sec):
            return None, f"Service {client.srv_name} not available"
        future = client.call_async(request)
        deadline = time.time() + timeout_sec
        while rclpy.ok() and not future.done() and time.time() < deadline:
            time.sleep(0.01)
        if not future.done():
            return None, f"Service {client.srv_name} timed out"
        try:
            return future.result(), ""
        except Exception as e:
            return None, str(e)

    def _set_node_params(self, client, param_dict, timeout_sec=3.0):
        req = SetParameters.Request()
        for name, val in param_dict.items():
            if isinstance(val, bool):
                pv = ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=val)
            elif isinstance(val, int):
                pv = ParameterValue(type=ParameterType.PARAMETER_INTEGER, integer_value=val)
            elif isinstance(val, float):
                pv = ParameterValue(type=ParameterType.PARAMETER_DOUBLE, double_value=val)
            else:
                pv = ParameterValue(type=ParameterType.PARAMETER_STRING, string_value=str(val))
            req.parameters.append(Parameter(name=name, value=pv))

        res, err = self._call_service_sync(client, req, timeout_sec=timeout_sec)
        if res is None:
            return False, err
        for r in res.results:
            if not r.successful:
                return False, r.reason or f"Failed setting parameter on {client.srv_name}"
        return True, ""

    def _call_trigger(self, client, timeout_sec=3.0):
        req = Trigger.Request()
        res, err = self._call_service_sync(client, req, timeout_sec=timeout_sec)
        if res is None:
            return False, err
        if not res.success:
            return False, res.message or f"Trigger {client.srv_name} returned False"
        return True, res.message

    def _wait_and_initialize(self):
        with self._cmd_lock:
            deadline = time.time() + 15.0
            required_clients = [
                self.client_mapper_params,
                self.client_server_params,
                self.client_mapper_save,
                self.client_mapper_clear,
            ]
            if self.use_virtual_geiger:
                required_clients.append(self.client_geiger_params)

            for client in required_clients:
                remaining = max(0.5, deadline - time.time())
                if not client.wait_for_service(timeout_sec=remaining):
                    self.get_logger().error(f"Startup failed: service {client.srv_name} did not appear.")
                    self._publish_status(last_command="init", last_result="error", error=f"Missing {client.srv_name}")
                    return

            self.ready = True
            self.get_logger().info("All radiation subsystem services are ready.")

            if self.initial_active:
                ok, err = self._do_set_active(True)
                if ok:
                    self._publish_status(last_command="rad_on", last_result="ok", error="")
                else:
                    self._publish_status(last_command="rad_on", last_result="error", error=err)
            else:
                self._publish_status(last_command="init", last_result="ok", error="")

    def _do_set_active(self, is_active: bool):
        ok_srv, err_srv = self._set_node_params(self.client_server_params, {'is_active': is_active})
        if not ok_srv:
            return False, err_srv

        self.field_active = is_active
        self.get_logger().info(f"Radiation field penalties set to: {'ON' if is_active else 'OFF'}")
        return True, ""

    def _do_set_geiger(self, is_active: bool, map_name: str = None):
        if not self.use_virtual_geiger:
            return False, "virtual_geiger node is not enabled in launch"
        params = {'is_active': is_active}
        if map_name:
            params['map_path'] = map_name
        ok_g, err_g = self._set_node_params(self.client_geiger_params, params)
        if not ok_g:
            return False, err_g
        self.geiger_active = is_active
        self.get_logger().info(
            f"Virtual Geiger set to: {'ON' if is_active else 'OFF'}"
            + (f" (map={map_name})" if map_name else "")
        )
        return True, ""

    def _handle_command_worker(self, cmd: str):
        with self._cmd_lock:
            if not self.ready:
                msg = "Radiation subsystem is still initializing"
                self.get_logger().warn(f"Cannot execute '{cmd}': {msg}")
                self._publish_status(last_command=cmd, last_result="error", error=msg)
                return

            parts = cmd.split(':', 1)
            action = parts[0].strip().lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if action == 'rad_on':
                ok, err = self._do_set_active(True)
                self._publish_status(last_command=cmd, last_result="ok" if ok else "error", error=err)

            elif action == 'rad_off':
                ok, err = self._do_set_active(False)
                self._publish_status(last_command=cmd, last_result="ok" if ok else "error", error=err)

            elif action == 'rad_geiger_on':
                map_arg = arg if arg else None
                if map_arg and not map_arg.endswith('.npy'):
                    map_arg += '.npy'
                ok, err = self._do_set_geiger(True, map_arg)
                self._publish_status(last_command=cmd, last_result="ok" if ok else "error", error=err)

            elif action == 'rad_geiger_off':
                ok, err = self._do_set_geiger(False)
                self._publish_status(last_command=cmd, last_result="ok" if ok else "error", error=err)

            elif action == 'rad_load':
                map_name = arg if arg else "explored_map.npy"
                if not map_name.endswith('.npy'):
                    map_name += '.npy'
                full_path = resolve_map_path(self.maps_dir, map_name)

                if not os.path.isfile(full_path):
                    err = f"Map file not found: {full_path}"
                    self.get_logger().error(err)
                    self._publish_status(last_command=cmd, last_result="error", error=err)
                    return

                try:
                    arr = np.load(full_path)
                    if arr.ndim != 2 or arr.size == 0:
                        raise ValueError("Invalid numpy map shape")
                except Exception as e:
                    err = f"Corrupt map file '{map_name}': {e}"
                    self.get_logger().error(err)
                    self._publish_status(last_command=cmd, last_result="error", error=err)
                    return

                # 1. Stop recording and load working map in mapper
                ok1, err1 = self._set_node_params(
                    self.client_mapper_params,
                    {'map_path': map_name, 'is_recording': False}
                )
                if not ok1:
                    self._publish_status(last_command=cmd, last_result="error", error=err1)
                    return

                # 2. Load working map in field server and activate field penalties
                ok2, err2 = self._set_node_params(
                    self.client_server_params,
                    {'map_path': map_name, 'is_active': True}
                )
                if not ok2:
                    self._publish_status(last_command=cmd, last_result="error", error=err2)
                    return

                # 3. Sync virtual geiger truth map path (without forcing it ON if operator keeps it OFF)
                if self.use_virtual_geiger and map_name != 'explored_map.npy' and not self.sensor_map_locked:
                    self._set_node_params(self.client_geiger_params, {'map_path': map_name})

                self.working_map = map_name
                self.recording = False
                self.field_active = True
                self.get_logger().info(f"Loaded radiation map '{map_name}' and enabled field.")
                self._publish_status(last_command=cmd, last_result="ok", error="")

            elif action == 'rad_source':
                if not self.use_virtual_geiger:
                    err = "Virtual geiger is disabled"
                    self.get_logger().warn(err)
                    self._publish_status(last_command=cmd, last_result="error", error=err)
                    return
                map_name = arg if arg else "radiation_map_complex.npy"
                if not map_name.endswith('.npy'):
                    map_name += '.npy'
                full_path = resolve_map_path(self.maps_dir, map_name)
                if not os.path.isfile(full_path):
                    err = f"Sensor map file not found: {full_path}"
                    self.get_logger().error(err)
                    self._publish_status(last_command=cmd, last_result="error", error=err)
                    return
                self.sensor_map_locked = True
                ok, err = self._do_set_geiger(True, map_name)
                self._publish_status(last_command=cmd, last_result="ok" if ok else "error", error=err)

            elif action == 'rad_record':
                map_name = arg if arg else "explored_map.npy"
                if not map_name.endswith('.npy'):
                    map_name += '.npy'

                # 1. Point mapper to map_name and start recording (loads existing data if file exists, or starts new)
                ok1, err1 = self._set_node_params(
                    self.client_mapper_params,
                    {'map_path': map_name, 'is_recording': True}
                )
                if not ok1:
                    self._publish_status(last_command=cmd, last_result="error", error=err1)
                    return

                # 2. Point field server to live SHM map so it updates on /radiation/map_updated triggers
                ok2, err2 = self._set_node_params(
                    self.client_server_params,
                    {'map_path': self.SHM_LIVE_MAP}
                )
                if not ok2:
                    self._publish_status(last_command=cmd, last_result="error", error=err2)
                    return

                self.working_map = map_name
                self.recording = True
                self.get_logger().info(f"Recording radiation map into '{map_name}' (live SHM active).")
                self._publish_status(last_command=cmd, last_result="ok", error="")

            elif action == 'rad_save':
                ok, err = self._call_trigger(self.client_mapper_save)
                if ok:
                    self.get_logger().info(f"Saved radiation map '{self.working_map}'.")
                    self._publish_status(last_command=cmd, last_result="ok", error="")
                else:
                    self.get_logger().error(f"Failed to save radiation map: {err}")
                    self._publish_status(last_command=cmd, last_result="error", error=err)

            elif action == 'rad_stop':
                # Stop recording and save accumulated map to disk; keep processes alive
                ok1, err1 = self._set_node_params(self.client_mapper_params, {'is_recording': False})
                if not ok1:
                    self._publish_status(last_command=cmd, last_result="error", error=err1)
                    return

                ok2, err2 = self._call_trigger(self.client_mapper_save)
                if not ok2:
                    self._publish_status(last_command=cmd, last_result="error", error=err2)
                    return

                # Point field server back to the saved disk map
                ok3, err3 = self._set_node_params(self.client_server_params, {'map_path': self.working_map})
                if not ok3:
                    self._publish_status(last_command=cmd, last_result="error", error=err3)
                    return

                self.recording = False
                self.get_logger().info(f"Stopped recording and saved '{self.working_map}'.")
                self._publish_status(last_command=cmd, last_result="ok", error="")

            elif action == 'rad_clear':
                ok, err = self._call_trigger(self.client_mapper_clear)
                if ok:
                    self.get_logger().info(f"Cleared radiation map '{self.working_map}'.")
                    self._publish_status(last_command=cmd, last_result="ok", error="")
                else:
                    self.get_logger().error(f"Failed to clear radiation map: {err}")
                    self._publish_status(last_command=cmd, last_result="error", error=err)

    def command_cb(self, msg: SmartCommand):
        if msg.target_system not in ('system', 'radiation'):
            return

        cmd = msg.command.strip()
        cmd_lower = cmd.lower()
        action = cmd_lower.split(':', 1)[0]

        allowed_actions = {
            'rad_on',
            'rad_off',
            'rad_geiger_on',
            'rad_geiger_off',
            'rad_load',
            'rad_source',
            'rad_record',
            'rad_save',
            'rad_stop',
            'rad_clear',
        }
        if action not in allowed_actions:
            return

        self.get_logger().info(f"Radiation Manager received command: '{cmd}'")
        threading.Thread(target=self._handle_command_worker, args=(cmd,), daemon=True).start()


def main(args=None):
    rclpy.init(args=args)
    node = RadiationManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
