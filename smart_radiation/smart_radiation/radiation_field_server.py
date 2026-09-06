#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import CompressedImage
from rcl_interfaces.msg import SetParametersResult
from rclpy.qos import QoSProfile, QoSDurabilityPolicy
import numpy as np
import cv2
import os
import json
from ament_index_python.packages import get_package_share_directory

class RadiationFieldServer(Node):
    def __init__(self):
        super().__init__('radiation_field_server')

        self.d_noise = 5.0       
        self.d_crit = 1000.0     
        self.k = 5.0             

        self.declare_parameter('map_path', 'explored_map.npy')
        map_path_param = self.get_parameter('map_path').value
        
        # DIRECT SRC LOAD using dynamic resolution
        pkg_share = get_package_share_directory('smart_radiation')
        src_dir = pkg_share.replace('install/smart_radiation/share/smart_radiation', 'src/smart_robotics/smart_radiation')
        base_dir = os.path.join(src_dir, 'maps')
        
        if not os.path.isabs(map_path_param):
            self.map_file = os.path.join(base_dir, map_path_param)
        else:
            self.map_file = map_path_param
            
        self.rad_ox = -20.0
        self.rad_oy = -20.0
        self.rad_res = 0.05
            
        self.load_map_from_disk()

        map_qos = QoSProfile(depth=1, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.trigger_sub = self.create_subscription(Empty, '/radiation/map_updated', self.trigger_cb, 10)
        self.map_sub = self.create_subscription(OccupancyGrid, '/map', self.map_callback, map_qos)
        self.rad_pub = self.create_publisher(OccupancyGrid, '/radiation_map', map_qos)
        self.image_pub = self.create_publisher(CompressedImage, '/radiation_image/compressed', map_qos)
        
        self.declare_parameter('is_active', False)
        self.is_active = False
        self.add_on_set_parameters_callback(self.param_callback)
        
        self.cached_width = 0
        self.cached_height = 0
        self.last_map_msg = None
        
        self.get_logger().info("ALARA Radiation Server started! Optimized for Raspberry Pi.")

    def param_callback(self, params):
        for param in params:
            if param.name == 'is_active':
                self.is_active = param.value
                self.publish_map()
            elif param.name == 'map_path':
                map_path_param = param.value
                if not os.path.isabs(map_path_param):
                    pkg_share = get_package_share_directory('smart_radiation')
                    src_dir = pkg_share.replace('install/smart_radiation/share/smart_radiation', 'src/smart_robotics/smart_radiation')
                    base_dir = os.path.join(src_dir, 'maps')
                    self.map_file = os.path.join(base_dir, map_path_param)
                else:
                    self.map_file = map_path_param
                self.load_map_from_disk()
                if self.last_map_msg is not None:
                    self.cached_width = 0
                    self.cached_height = 0
                    self.map_callback(self.last_map_msg)
        return SetParametersResult(successful=True)

    def load_map_from_disk(self):
        try:
            self.raw_dose_map = np.load(self.map_file)
            self.get_logger().info(f"Successfully loaded Live Map: {self.raw_dose_map.shape}")
        except Exception as e:
            self.get_logger().warn(f"Map {self.map_file} not found. Awaiting mapper generation.")
            self.raw_dose_map = np.zeros((800, 800), dtype=np.float32)

        base_dir = os.path.dirname(self.map_file)
        base_name = os.path.splitext(os.path.basename(self.map_file))[0]
        meta_file = os.path.join(base_dir, f"{base_name}_meta.json")
        
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r') as f:
                    meta = json.load(f)
                    self.rad_ox = meta.get('ox', self.rad_ox)
                    self.rad_oy = meta.get('oy', self.rad_oy)
                    self.rad_res = meta.get('res', self.rad_res)
                self.get_logger().info(f"Loaded Live Meta: origin=({self.rad_ox}, {self.rad_oy})")
            except Exception as e:
                pass

    def trigger_cb(self, msg):
        self.load_map_from_disk()
        if self.last_map_msg is not None:
            self.cached_width = 0
            self.cached_height = 0
            self.map_callback(self.last_map_msg)

    def map_callback(self, map_msg):
        if self.raw_dose_map is None:
            return

        self.last_map_msg = map_msg
        width = map_msg.info.width
        height = map_msg.info.height

        if width != self.cached_width or height != self.cached_height:
            
            working_dose_map = np.zeros((height, width), dtype=np.float32)
            
            res = map_msg.info.resolution
            map_origin_x = map_msg.info.origin.position.x
            map_origin_y = map_msg.info.origin.position.y
            
            offset_x = int((self.rad_ox - map_origin_x) / res)
            offset_y = int((self.rad_oy - map_origin_y) / res)
            
            rad_h, rad_w = self.raw_dose_map.shape
            
            start_x = max(0, offset_x)
            start_y = max(0, offset_y)
            end_x = min(width, offset_x + rad_w)
            end_y = min(height, offset_y + rad_h)
            
            if end_x > start_x and end_y > start_y:
                rad_start_x = start_x - offset_x
                rad_start_y = start_y - offset_y
                rad_end_x = rad_start_x + (end_x - start_x)
                rad_end_y = rad_start_y + (end_y - start_y)
                
                working_dose_map[start_y:end_y, start_x:end_x] = \
                    self.raw_dose_map[rad_start_y:rad_end_y, rad_start_x:rad_end_x]

            cost_field = np.zeros_like(working_dose_map)
            mask_active = (working_dose_map > self.d_noise) & (working_dose_map < self.d_crit)
            
            if np.any(mask_active):
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

        heatmap_gray = (final_grid * 255.0 / 100.0).astype(np.uint8)
        heatmap_color = cv2.applyColorMap(heatmap_gray, cv2.COLORMAP_TURBO)
        
        b, g, r = cv2.split(heatmap_color)
        alpha = np.full(b.shape, 160, dtype=np.uint8)
        
        alpha[final_grid <= 0] = 0
        alpha[slam_map == -1] = 0
        
        rgba = cv2.merge((b, g, r, alpha))
        rgba = cv2.flip(rgba, 0)
        
        success, encoded_image = cv2.imencode('.png', rgba)
        if success:
            img_msg = CompressedImage()
            img_msg.header = rad_msg.header
            img_msg.format = 'png'
            img_msg.data = encoded_image.tobytes()
            self.image_pub.publish(img_msg)

def main(args=None):
    rclpy.init(args=args)
    node = RadiationFieldServer()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()