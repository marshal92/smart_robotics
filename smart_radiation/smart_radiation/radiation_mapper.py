#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Empty
from std_srvs.srv import Trigger
from rcl_interfaces.msg import SetParametersResult
import tf2_ros
import numpy as np
import os
import math
import time
import json
from ament_index_python.packages import get_package_share_directory

class RadiationMapper(Node):
    def __init__(self):
        super().__init__('radiation_mapper')

        self.declare_parameter('map_path', 'explored_map.npy')
        self.map_path_param = self.get_parameter('map_path').value
        
        self.declare_parameter('is_recording', False)
        self.is_recording = self.get_parameter('is_recording').value
        
        self.declare_parameter('width', 800)
        self.declare_parameter('height', 800)
        self.declare_parameter('res', 0.05)
        self.declare_parameter('ox', -20.0)
        self.declare_parameter('oy', -20.0)
        
        self.width = self.get_parameter('width').value
        self.height = self.get_parameter('height').value
        self.res = self.get_parameter('res').value
        self.ox = self.get_parameter('ox').value
        self.oy = self.get_parameter('oy').value

        self.map_grid = np.zeros((self.height, self.width), dtype=np.float32)
        self.weight_grid = np.zeros((self.height, self.width), dtype=np.float32)
        
        self.map_dirty = False
        self.last_saved_pose = None
        self.last_saved_dose = None

        self._resolve_paths(self.map_path_param)
        self._load_map()

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        self.dose_sub = self.create_subscription(Float32, '/radiation/dose', self.dose_cb, 10)
        self.trigger_pub = self.create_publisher(Empty, '/radiation/map_updated', 10)
        
        self.save_srv = self.create_service(Trigger, '~/save_map', self.save_map_cb)
        self.clear_srv = self.create_service(Trigger, '~/clear_map', self.clear_map_cb)

        self.shm_file = "/dev/shm/live_rad_map.npy"
        self.shm_meta = "/dev/shm/live_rad_map_meta.json"

        self.add_on_set_parameters_callback(self.param_callback)

        self.create_timer(2.0, self._timer_shm_update)
        self.create_timer(60.0, self._timer_disk_save)

        self.get_logger().info(f"Radiation Mapper started. Recording: {self.is_recording}")

    def param_callback(self, params):
        for param in params:
            if param.name == 'is_recording':
                self.is_recording = param.value
                self.get_logger().info(f"Recording state changed to: {self.is_recording}")
                if self.is_recording:
                    self.map_dirty = True
                    self._timer_shm_update()
            elif param.name == 'map_path':
                new_path = param.value
                if new_path != self.map_path_param:
                    self.get_logger().info(f"Map path changing to: {new_path}. Saving current map first...")
                    self._save_map()
                    self.map_path_param = new_path
                    self._resolve_paths(new_path)
                    self._load_map()
                    self.map_dirty = True
                    self._timer_shm_update()
        return SetParametersResult(successful=True)

    def save_map_cb(self, request, response):
        self.get_logger().info("Service call received: Force Saving Map")
        self._save_map()
        response.success = True
        response.message = f"Map saved to {self.map_file}"
        return response

    def clear_map_cb(self, request, response):
        self.get_logger().warn("Service call received: Clearing Live Radiation Map")
        self.map_grid = np.zeros((self.height, self.width), dtype=np.float32)
        self.weight_grid = np.zeros((self.height, self.width), dtype=np.float32)
        self.last_saved_pose = None
        self.last_saved_dose = None
        self.map_dirty = True
        self._timer_shm_update()
        response.success = True
        response.message = "Map cleared in memory."
        return response

    def _resolve_paths(self, map_path_param):
        pkg_share = get_package_share_directory('smart_radiation')
        src_dir = pkg_share.replace('install/smart_radiation/share/smart_radiation', 'src/smart_robotics/smart_radiation')
        base_dir = os.path.join(src_dir, 'maps')
        os.makedirs(base_dir, exist_ok=True)
        
        if not os.path.isabs(map_path_param):
            self.map_file = os.path.join(base_dir, map_path_param)
        else:
            self.map_file = map_path_param
            base_dir = os.path.dirname(self.map_file)
            
        base_name = os.path.splitext(os.path.basename(self.map_file))[0]
        self.weight_file = os.path.join(base_dir, f"{base_name}_weights.npy")
        self.log_file = os.path.join(base_dir, f"{base_name}_raw_log.csv")
        self.meta_file = os.path.join(base_dir, f"{base_name}_meta.json")

    def _load_map(self):
        self.get_logger().info(f"Attempting to load map from {self.map_file}")
        
        if os.path.exists(self.map_file):
            try:
                self.map_grid = np.load(self.map_file)
                self.get_logger().info(f"Loaded existing map {self.map_grid.shape}")
                
                if os.path.exists(self.meta_file):
                    with open(self.meta_file, 'r') as f:
                        meta = json.load(f)
                        self.width = meta.get('width', self.width)
                        self.height = meta.get('height', self.height)
                        self.ox = meta.get('ox', self.ox)
                        self.oy = meta.get('oy', self.oy)
                        self.res = meta.get('res', self.res)
                
                # Check for weights file
                if os.path.exists(self.weight_file):
                    self.weight_grid = np.load(self.weight_file)
                else:
                    self.weight_grid = np.zeros_like(self.map_grid)
                    self.weight_grid[self.map_grid > 0.0] = 1.0
                    self.get_logger().info("No weights file found. Generated synthetic weights.")
            except Exception as e:
                self.get_logger().error(f"Failed to load map, starting fresh: {e}")
                self.map_grid = np.zeros((self.height, self.width), dtype=np.float32)
                self.weight_grid = np.zeros((self.height, self.width), dtype=np.float32)
        else:
            self.get_logger().info(f"Map file not found. Initializing zeros.")
            self.map_grid = np.zeros((self.height, self.width), dtype=np.float32)
            self.weight_grid = np.zeros((self.height, self.width), dtype=np.float32)

        self._save_meta()
        self.map_dirty = False
        
        if not os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'w') as f:
                    f.write("Timestamp,X,Y,Dose\n")
            except Exception:
                pass

    def _save_meta(self):
        meta = {
            "width": self.width,
            "height": self.height,
            "res": self.res,
            "ox": self.ox,
            "oy": self.oy
        }
        try:
            with open(self.meta_file, 'w') as f:
                json.dump(meta, f)
        except Exception as e:
            self.get_logger().error(f"Failed to save meta: {e}")

    def _timer_shm_update(self):
        if self.map_dirty:
            try:
                np.save(self.shm_file, self.map_grid)
                meta = {"width": self.width, "height": self.height, "res": self.res, "ox": self.ox, "oy": self.oy}
                with open(self.shm_meta, 'w') as f:
                    json.dump(meta, f)
                if hasattr(self, 'trigger_pub'):
                    self.trigger_pub.publish(Empty())
                self.map_dirty = False
            except Exception as e:
                self.get_logger().error(f"SHM write failed: {e}")

    def _timer_disk_save(self):
        if self.is_recording:
            self._save_map()

    def _save_map(self):
        try:
            temp_file = self.map_file + "_temp.npy"
            np.save(temp_file, self.map_grid)
            os.replace(temp_file, self.map_file)
            
            temp_w_file = self.weight_file + "_temp.npy"
            np.save(temp_w_file, self.weight_grid)
            os.replace(temp_w_file, self.weight_file)
            self.get_logger().info(f"Map successfully saved to disk.")
        except Exception as e:
            self.get_logger().error(f"Error saving map: {e}")

    def dose_cb(self, msg):
        if not self.is_recording:
            return

        current_dose = msg.data

        try:
            trans = self.tf_buffer.lookup_transform('map', 'base_footprint', rclpy.time.Time())
            rx = trans.transform.translation.x
            ry = trans.transform.translation.y
        except Exception as e:
            return

        try:
            with open(self.log_file, 'a') as f:
                f.write(f"{time.time():.3f},{rx:.3f},{ry:.3f},{current_dose:.3f}\n")
        except Exception as e:
            pass

        if self.last_saved_pose is not None and self.last_saved_dose is not None:
            dx = rx - self.last_saved_pose[0]
            dy = ry - self.last_saved_pose[1]
            dist = math.sqrt(dx**2 + dy**2)
            
            if self.last_saved_dose > 0:
                dose_diff_pct = abs(current_dose - self.last_saved_dose) / self.last_saved_dose
            else:
                dose_diff_pct = 1.0 if current_dose > 0 else 0.0
                
            if dist < 0.2 and dose_diff_pct < 0.15:
                return 

        self.last_saved_pose = (rx, ry)
        self.last_saved_dose = current_dose

        rad_x = int((rx - self.ox) / self.res)
        rad_y = int((ry - self.oy) / self.res)

        roi_radius = int(1.0 / self.res) 

        x_min = max(0, rad_x - roi_radius)
        x_max = min(self.width, rad_x + roi_radius + 1)
        y_min = max(0, rad_y - roi_radius)
        y_max = min(self.height, rad_y + roi_radius + 1)

        if x_min >= x_max or y_min >= y_max:
            return 

        xv, yv = np.meshgrid(np.arange(x_min, x_max), np.arange(y_min, y_max))
        dist_sq = ((xv - rad_x) * self.res)**2 + ((yv - rad_y) * self.res)**2
        
        sigma = 0.5 
        spot = current_dose * np.exp(-dist_sq / (2 * sigma**2))
        
        mask = np.exp(-dist_sq / (2 * (sigma/2)**2))
        mask = np.clip(mask, 0.0, 1.0)

        roi_slice = (slice(y_min, y_max), slice(x_min, x_max))
        
        old_weight = self.weight_grid[roi_slice]
        new_weight = old_weight + mask
        new_weight_safe = np.maximum(new_weight, 1e-6)
        
        self.map_grid[roi_slice] = (self.map_grid[roi_slice] * old_weight + spot * mask) / new_weight_safe
        self.weight_grid[roi_slice] = np.clip(new_weight, 0.0, 10.0)

        self.map_dirty = True
        self.get_logger().debug(f"Blended spot at ({rad_x}, {rad_y})")

def main(args=None):
    rclpy.init(args=args)
    node = RadiationMapper()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._save_map()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
