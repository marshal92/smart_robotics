#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid
import numpy as np
import os
from ament_index_python.packages import get_package_share_directory
from rclpy.qos import QoSProfile, QoSDurabilityPolicy
from rcl_interfaces.msg import SetParametersResult

class RadiationFieldServer(Node):
    def __init__(self):
        super().__init__('radiation_field_server')

        self.d_noise = 5.0       
        self.d_crit = 1000.0     
        self.k = 5.0             

        try:
            pkg_share = get_package_share_directory('smart_radiation')
            map_path = os.path.join(pkg_share, 'maps', 'radiation_map.npy')
            self.raw_dose_map = np.load(map_path)
            self.get_logger().info(f"Successfully loaded physical map: {self.raw_dose_map.shape}")
        except Exception as e:
            self.get_logger().error(f"Error loading radiation_map.npy: {e}")
            self.raw_dose_map = None

        map_qos = QoSProfile(depth=1, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.map_sub = self.create_subscription(OccupancyGrid, '/map', self.map_callback, map_qos)
        self.rad_pub = self.create_publisher(OccupancyGrid, '/radiation_map', map_qos)
        
        self.declare_parameter('is_active', False)
        self.is_active = False
        self.add_on_set_parameters_callback(self.param_callback)
        
        self.cached_width = 0
        self.cached_height = 0
        self.last_map_msg = None
        
        self.get_logger().info("ALARA Radiation Server (Clean Sigmoid) started!")

    def param_callback(self, params):
        for param in params:
            if param.name == 'is_active':
                self.is_active = param.value
                self.get_logger().info(f"Radiation: {'ON' if self.is_active else 'OFF'}")
                self.publish_map()
        return SetParametersResult(successful=True)

    def map_callback(self, map_msg):
        if self.raw_dose_map is None:
            return

        self.last_map_msg = map_msg
        width = map_msg.info.width
        height = map_msg.info.height

        if width != self.cached_width or height != self.cached_height:
            self.get_logger().info(f"Syncing SLAM map {width}x{height} with radiation matrix...")
            
            working_dose_map = np.zeros((height, width), dtype=np.float32)
            min_h = min(height, self.raw_dose_map.shape[0])
            min_w = min(width, self.raw_dose_map.shape[1])
            working_dose_map[:min_h, :min_w] = self.raw_dose_map[:min_h, :min_w]

            cost_field = np.zeros_like(working_dose_map)
            mask_active = (working_dose_map > self.d_noise) & (working_dose_map < self.d_crit)
            
            norm = (working_dose_map[mask_active] - self.d_noise) / (self.d_crit - self.d_noise)
            norm = np.clip(norm, 0.0, 1.0)
            center = 0.5
            
            min_sig = 1.0 / (1.0 + np.exp(-self.k * (0.0 - center)))
            max_sig = 1.0 / (1.0 + np.exp(-self.k * (1.0 - center)))
            raw_sig = 1.0 / (1.0 + np.exp(-self.k * (norm - center)))
            
            penalty = 100.0 * (raw_sig - min_sig) / (max_sig - min_sig)
            cost_field[mask_active] = penalty
            cost_field[working_dose_map >= self.d_crit] = 100.0 
            
            self.cached_100_grid = np.round(cost_field).astype(np.int8)

            self.cached_width = width
            self.cached_height = height
            self.publish_map()

    def publish_map(self):
        if self.last_map_msg is None or not hasattr(self, 'cached_100_grid'):
            return

        if self.is_active:
            final_grid = np.copy(self.cached_100_grid)
        else:
            final_grid = np.zeros((self.cached_height, self.cached_width), dtype=np.int8)

        slam_map = np.array(self.last_map_msg.data).reshape((self.cached_height, self.cached_width))
        final_grid[slam_map == -1] = -1

        rad_msg = OccupancyGrid()
        rad_msg.header = self.last_map_msg.header
        rad_msg.header.stamp = self.get_clock().now().to_msg()
        rad_msg.info = self.last_map_msg.info
        rad_msg.data = final_grid.flatten().tolist()
        
        self.rad_pub.publish(rad_msg)

def main(args=None):
    rclpy.init(args=args)
    node = RadiationFieldServer()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()