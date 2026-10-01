#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from nav_msgs.msg import OccupancyGrid
from rcl_interfaces.msg import SetParametersResult
from rclpy.qos import QoSProfile, QoSDurabilityPolicy
import tf2_ros
import os
import json
import numpy as np
from ament_index_python.packages import get_package_share_directory

class VirtualGeigerWorker(Node):
    def __init__(self, use_sim_time=True):
        from rclpy.parameter import Parameter
        super().__init__('virtual_geiger_worker', parameter_overrides=[Parameter('use_sim_time', Parameter.Type.BOOL, use_sim_time)])
        self.pub = self.create_publisher(Float32, '/radiation/dose', 10)
        self.raw_dose_map = None
        self.rad_ox = -20.0
        self.rad_oy = -20.0
        self.rad_res = 0.05
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.create_timer(0.2, self.loop)
        self.get_logger().info("Virtual Geiger Worker active.")

    def load_truth_map(self, map_file_name):
        try:
            pkg_share = get_package_share_directory('smart_radiation')
            src_dir = pkg_share.replace('install/smart_radiation/share/smart_radiation', 'src/smart_robotics/smart_radiation')
            base_dir = os.path.join(src_dir, 'maps')
            
            map_path = map_file_name if os.path.isabs(map_file_name) else os.path.join(base_dir, map_file_name)
            base_name = os.path.splitext(os.path.basename(map_path))[0]
            meta_path = os.path.join(os.path.dirname(map_path), f"{base_name}_meta.json")

            if os.path.exists(map_path):
                self.raw_dose_map = np.load(map_path)
                if os.path.exists(meta_path):
                    with open(meta_path, 'r') as f:
                        meta = json.load(f)
                        self.rad_ox, self.rad_oy, self.rad_res = meta.get('ox', self.rad_ox), meta.get('oy', self.rad_oy), meta.get('res', self.rad_res)
            else:
                self.raw_dose_map = np.zeros((800, 800), dtype=np.float32)
        except Exception as e:
            self.get_logger().error(f"Error loading map: {e}")

    def loop(self):
        if self.raw_dose_map is None: return
        try:
            trans = self.tf_buffer.lookup_transform('map', 'base_footprint', rclpy.time.Time())
            rx, ry = trans.transform.translation.x, trans.transform.translation.y
        except Exception:
            return
        rad_x = int((rx - self.rad_ox) / self.rad_res)
        rad_y = int((ry - self.rad_oy) / self.rad_res)
        max_y, max_x = self.raw_dose_map.shape
        dose_val = float(self.raw_dose_map[rad_y, rad_x]) if 0 <= rad_x < max_x and 0 <= rad_y < max_y else 0.0
        msg = Float32()
        msg.data = dose_val
        self.pub.publish(msg)

class VirtualGeigerManager(Node):
    def __init__(self):
        from rclpy.parameter import Parameter
        super().__init__('virtual_geiger', parameter_overrides=[Parameter('use_sim_time', Parameter.Type.BOOL, False)])
        
        self.declare_parameter('worker_use_sim_time', True)
        self.worker_sim_time = self.get_parameter('worker_use_sim_time').value
        self.declare_parameter('map_path', 'radiation_map.npy')
        self.map_path_param = self.get_parameter('map_path').value
        self.declare_parameter('is_active', False)
        
        self.worker = None
        self.executor_thread = None
        self.executor = None
        
        self.add_on_set_parameters_callback(self.param_callback)
        self.pub = self.create_publisher(Float32, '/radiation/dose', 10)
        self.set_parameters([Parameter('use_sim_time', Parameter.Type.BOOL, False)])
        self.get_logger().info("Virtual Geiger Manager started (Idle CPU = 0%)")
        self._apply_state(self.get_parameter('is_active').value)

    def _apply_state(self, is_active):
        if is_active and self.worker is None:
            self.worker = VirtualGeigerWorker(use_sim_time=self.worker_sim_time)
            self.worker.load_truth_map(self.map_path_param)
            self.executor = rclpy.executors.SingleThreadedExecutor()
            self.executor.add_node(self.worker)
            self.executor_thread = __import__('threading').Thread(target=self.executor.spin, daemon=True)
            self.executor_thread.start()
        elif not is_active and self.worker is not None:
            self.executor.shutdown()
            self.executor_thread.join()
            self.worker.destroy_node()
            self.worker = None
            self.executor = None
            msg = Float32()
            msg.data = 0.0
            self.pub.publish(msg)

    def param_callback(self, params):
        for param in params:
            if param.name == 'is_active':
                self._apply_state(param.value)
            elif param.name == 'map_path':
                self.map_path_param = param.value
                if self.worker is not None:
                    self.worker.load_truth_map(self.map_path_param)
        return SetParametersResult(successful=True)

def strip_sim_time(args):
    if args is None:
        import sys
        args = sys.argv
    clean_args = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg == '--ros-args':
            clean_args.append(arg)
        elif arg == '-p' or arg == '--param':
            clean_args.append(arg)
        elif arg.startswith('use_sim_time:='):
            if len(clean_args) > 0 and clean_args[-1] in ('-p', '--param'):
                clean_args.pop()
        elif arg == 'use_sim_time':
            if len(clean_args) > 0 and clean_args[-1] in ('-p', '--param'):
                clean_args.pop()
            skip_next = True
        else:
            clean_args.append(arg)
    return clean_args

def main(args=None):
    clean_args = strip_sim_time(args)
    rclpy.init(args=clean_args)
    manager = VirtualGeigerManager()
    try:
        import time
        while rclpy.ok():
            rclpy.spin_once(manager, timeout_sec=0.1)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        if manager.worker is not None:
            manager.executor.shutdown()
            manager.executor_thread.join()
            manager.worker.destroy_node()
        manager.destroy_node()
        if rclpy.ok(): rclpy.shutdown()

if __name__ == '__main__':
    main()
