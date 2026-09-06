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

class VirtualGeiger(Node):
    def __init__(self):
        super().__init__('virtual_geiger')

        self.pub = self.create_publisher(Float32, '/radiation/dose', 10)
        
        self.declare_parameter('map_path', 'radiation_map.npy')
        self.map_path_param = self.get_parameter('map_path').value
        
        self.declare_parameter('is_active', False)
        self.is_active = self.get_parameter('is_active').value
        
        self.add_on_set_parameters_callback(self.param_callback)
        
        self.raw_dose_map = None
        self.rad_ox = -20.0
        self.rad_oy = -20.0
        self.rad_res = 0.05

        self._load_truth_map(self.map_path_param)

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        self.create_timer(0.2, self.loop)
        self.get_logger().info("Virtual Geiger Counter started (Simulation Mode).")

    def param_callback(self, params):
        for param in params:
            if param.name == 'is_active':
                self.is_active = param.value
                self.get_logger().info(f"Virtual Geiger active: {self.is_active}")
            elif param.name == 'map_path':
                new_path = param.value
                if new_path != self.map_path_param:
                    self.map_path_param = new_path
                    self._load_truth_map(new_path)
        return SetParametersResult(successful=True)

    def _load_truth_map(self, map_file_name):
        try:
            pkg_share = get_package_share_directory('smart_radiation')
            src_dir = pkg_share.replace('install/smart_radiation/share/smart_radiation', 'src/smart_robotics/smart_radiation')
            base_dir = os.path.join(src_dir, 'maps')
            
            if not os.path.isabs(map_file_name):
                map_path = os.path.join(base_dir, map_file_name)
            else:
                map_path = map_file_name
                
            base_name = os.path.splitext(os.path.basename(map_path))[0]
            meta_path = os.path.join(os.path.dirname(map_path), f"{base_name}_meta.json")

            if os.path.exists(map_path):
                self.raw_dose_map = np.load(map_path)
                self.get_logger().info(f"Loaded simulation truth map: {self.raw_dose_map.shape}")
                
                if os.path.exists(meta_path):
                    with open(meta_path, 'r') as f:
                        meta = json.load(f)
                        self.rad_ox = meta.get('ox', self.rad_ox)
                        self.rad_oy = meta.get('oy', self.rad_oy)
                        self.rad_res = meta.get('res', self.rad_res)
            else:
                self.get_logger().warn(f"Truth map not found: {map_path}. Generating zeros.")
                self.raw_dose_map = np.zeros((800, 800), dtype=np.float32)
                
        except Exception as e:
            self.get_logger().error(f"Error loading simulation map: {e}")

    def loop(self):
        if not self.is_active:
            msg = Float32()
            msg.data = 0.0
            self.pub.publish(msg)
            return

        if self.raw_dose_map is None:
            return

        try:
            trans = self.tf_buffer.lookup_transform('map', 'base_footprint', rclpy.time.Time())
            rx = trans.transform.translation.x
            ry = trans.transform.translation.y
        except Exception:
            return

        rad_x = int((rx - self.rad_ox) / self.rad_res)
        rad_y = int((ry - self.rad_oy) / self.rad_res)

        max_y, max_x = self.raw_dose_map.shape
        dose_val = 0.0
        
        if 0 <= rad_x < max_x and 0 <= rad_y < max_y:
            dose_val = float(self.raw_dose_map[rad_y, rad_x])

        msg = Float32()
        msg.data = dose_val
        self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = VirtualGeiger()
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
