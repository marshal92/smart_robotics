#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import CompressedImage
from rcl_interfaces.msg import SetParametersResult
from rclpy.qos import QoSProfile, QoSDurabilityPolicy
import numpy as np
import cv2
import os
import json
from ament_index_python.packages import get_package_share_directory

class BaselineFieldServer(Node):
    def __init__(self):
        super().__init__('baseline_field_server')

        self.declare_parameter('map_path', 'radiation_map_complex.npy')
        self.declare_parameter('radiation_threshold', 500.0)
        self.declare_parameter('radiation_cost', 87) # 87 in OccupancyGrid -> ~220 in Nav2 Costmap (with trinary_costmap: false)
        self.declare_parameter('is_active', False)
        
        self.map_path_param = self.get_parameter('map_path').value
        self.radiation_threshold = self.get_parameter('radiation_threshold').value
        self.radiation_cost = self.get_parameter('radiation_cost').value
        self.is_active = self.get_parameter('is_active').value
        
        self._resolve_map_path()
            
        self.rad_ox = -20.0
        self.rad_oy = -20.0
        self.rad_res = 0.05
        self.raw_dose_map = None
        self.last_map_msg = None
            
        self.load_map_from_disk()

        map_qos = QoSProfile(depth=1, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.map_sub = self.create_subscription(OccupancyGrid, '/map', self.map_callback, map_qos)
        self.baseline_pub = self.create_publisher(OccupancyGrid, '/baseline_map', map_qos)
        self.image_pub = self.create_publisher(CompressedImage, '/radiation_image/compressed', map_qos)
        
        self.add_on_set_parameters_callback(self.param_callback)
        
        self.get_logger().info(f"Baseline Server started! Threshold: {self.radiation_threshold}")

    def _resolve_map_path(self):
        if not os.path.isabs(self.map_path_param):
            base_dir = '/home/oleksandr/ros2_ws/src/smart_robotics/smart_radiation/maps'
            self.map_file = os.path.join(base_dir, self.map_path_param)
        else:
            self.map_file = self.map_path_param

    def param_callback(self, params):
        for param in params:
            if param.name == 'is_active':
                self.is_active = param.value
                self.publish_map()
            elif param.name == 'radiation_threshold':
                self.radiation_threshold = param.value
                self.get_logger().info(f"Updated radiation threshold to {self.radiation_threshold}")
                if self.last_map_msg is not None:
                    self.map_callback(self.last_map_msg)
            elif param.name == 'radiation_cost':
                self.radiation_cost = param.value
                self.get_logger().info(f"Updated radiation cost to {self.radiation_cost}")
                if self.last_map_msg is not None:
                    self.map_callback(self.last_map_msg)
            elif param.name == 'map_path':
                self.map_path_param = param.value
                self._resolve_map_path()
                self.load_map_from_disk()
                if self.last_map_msg is not None:
                    self.map_callback(self.last_map_msg)
        return SetParametersResult(successful=True)

    def load_map_from_disk(self):
        try:
            self.raw_dose_map = np.load(self.map_file)
            self.get_logger().info(f"Successfully loaded Live Map: {self.raw_dose_map.shape}")
        except Exception as e:
            self.get_logger().error(f"Map {self.map_file} not found. Cannot proceed without valid map.")
            self.raw_dose_map = None
            return

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
                self.get_logger().warn("Meta file not found, using default origin and resolution.")

    def map_callback(self, map_msg):
        if self.raw_dose_map is None:
            return

        self.last_map_msg = map_msg
        width = map_msg.info.width
        height = map_msg.info.height
        res = map_msg.info.resolution
        
        if abs(res - self.rad_res) > 1e-4:
            self.get_logger().error("Resolution mismatch between map and radiation grid!")
            return

        map_origin_x = map_msg.info.origin.position.x
        map_origin_y = map_msg.info.origin.position.y
        
        working_dose_map = np.zeros((height, width), dtype=np.float32)
        
        offset_x = int(round((self.rad_ox - map_origin_x) / res))
        offset_y = int(round((self.rad_oy - map_origin_y) / res))
        
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

        slam_map = np.array(map_msg.data).reshape((height, width))
        
        # Start with a mask of 0
        cost_field = np.zeros((height, width), dtype=np.int8)
        
        # Where radiation is high AND we know space is free, put the specified cost
        mask_contaminated = working_dose_map >= self.radiation_threshold
        mask_free = slam_map == 0
        
        cost_field[mask_contaminated & mask_free] = self.radiation_cost
        
        self.cached_100_grid = cost_field
        self.cached_width = width
        self.cached_height = height
        
        self.publish_map()

    def publish_map(self):
        if self.last_map_msg is None or not hasattr(self, 'cached_100_grid'):
            return

        slam_map = np.array(self.last_map_msg.data).reshape((self.cached_height, self.cached_width))
        final_grid = np.copy(slam_map)
        
        if self.is_active:
            # Overlay baseline virtual radiation. Only on free space so we don't erase real walls.
            mask_apply = (self.cached_100_grid == self.radiation_cost) & (final_grid == 0)
            final_grid[mask_apply] = self.radiation_cost

        baseline_msg = OccupancyGrid()
        baseline_msg.header = self.last_map_msg.header
        baseline_msg.header.stamp = self.get_clock().now().to_msg()
        baseline_msg.info = self.last_map_msg.info
        baseline_msg.data = final_grid.flatten().tolist()
        
        self.baseline_pub.publish(baseline_msg)

        # Web UI visualizer (normalize the cost to 255 for color mapping)
        heatmap_gray = (self.cached_100_grid * 255.0 / max(1, self.radiation_cost)).astype(np.uint8)
        heatmap_color = cv2.applyColorMap(heatmap_gray, cv2.COLORMAP_TURBO)
        
        b, g, r = cv2.split(heatmap_color)
        alpha = np.full(b.shape, 160, dtype=np.uint8)
        
        if self.is_active:
            alpha[self.cached_100_grid <= 0] = 0
            alpha[slam_map == -1] = 0
        else:
            alpha.fill(0) # Hide image if rad is off
        
        rgba = cv2.merge((b, g, r, alpha))
        rgba = cv2.flip(rgba, 0) # Gazebo coordinate flip
        
        success, encoded_image = cv2.imencode('.png', rgba)
        if success:
            img_msg = CompressedImage()
            img_msg.header = baseline_msg.header
            img_msg.format = 'png'
            img_msg.data = encoded_image.tobytes()
            self.image_pub.publish(img_msg)

def main(args=None):
    rclpy.init(args=args)
    node = BaselineFieldServer()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
