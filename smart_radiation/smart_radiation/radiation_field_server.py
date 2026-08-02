#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import CompressedImage
import numpy as np
import cv2
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
        self.image_pub = self.create_publisher(CompressedImage, '/radiation_image/compressed', map_qos)
        
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
            
            # Real-world alignment
            res = map_msg.info.resolution
            map_origin_x = map_msg.info.origin.position.x
            map_origin_y = map_msg.info.origin.position.y
            
            # The radiation map was generated with these offsets (from view_map.py)
            rad_origin_x = -5.0024
            rad_origin_y = -4.63
            
            # Calculate pixel offsets
            offset_x = int((rad_origin_x - map_origin_x) / res)
            offset_y = int((rad_origin_y - map_origin_y) / res)
            
            rad_h, rad_w = self.raw_dose_map.shape
            
            # Place the radiation map into the working dose map at the correct offset
            for y in range(rad_h):
                for x in range(rad_w):
                    target_y = offset_y + y
                    target_x = offset_x + x
                    if 0 <= target_y < height and 0 <= target_x < width:
                        working_dose_map[target_y, target_x] = self.raw_dose_map[y, x]

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

        # Publish CompressedImage PNG for 3D Digital Twin Overlay
        # We always publish the image so the UI can just toggle visibility
        # Map 0-100 penalty to 0-255
        heatmap_gray = (final_grid * 255.0 / 100.0).astype(np.uint8)
        heatmap_color = cv2.applyColorMap(heatmap_gray, cv2.COLORMAP_TURBO)
        
        # Create RGBA
        b, g, r = cv2.split(heatmap_color)
        alpha = np.full(b.shape, 160, dtype=np.uint8) # semi-transparent
        
        # Hide pixels with 0 penalty or unknown SLAM map
        alpha[final_grid <= 0] = 0
        alpha[slam_map == -1] = 0
        
        rgba = cv2.merge((b, g, r, alpha))
        
        # Flip vertically to match the SLAM map's orientation in the Web UI
        rgba = cv2.flip(rgba, 0)
        
        # Encode as PNG (keeps alpha)
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
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()