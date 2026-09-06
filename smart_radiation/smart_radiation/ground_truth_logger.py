#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import tf2_ros
import os
import json
import numpy as np
import time
from datetime import datetime
from ament_index_python.packages import get_package_share_directory

class GroundTruthLogger(Node):
    def __init__(self):
        super().__init__('ground_truth_logger')

        self.declare_parameter('map_path', 'radiation_test_1.npy')
        self.map_file_name = self.get_parameter('map_path').value

        self.raw_dose_map = None
        self.rad_ox = -20.0
        self.rad_oy = -20.0
        self.rad_res = 0.05
        
        self.total_dose_accumulated = 0.0
        self.last_time = None

        pkg_share = get_package_share_directory('smart_radiation')
        src_dir = pkg_share.replace('install/smart_radiation/share/smart_radiation', 'src/smart_robotics/smart_radiation')
        
        # Загружаем карту
        self._load_truth_map(src_dir)

        # Создаем папку для логов
        log_dir = os.path.join(src_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = os.path.join(log_dir, f"ground_truth_{timestamp}.csv")
        
        with open(self.log_file, 'w') as f:
            f.write("Time,X,Y,DoseRate_mSv_h,Accumulated_TID_uSv\n")
            
        self.get_logger().info(f"Ground Truth Logger started. Logging to {self.log_file}")

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # 10 Hz цикл (как delta_t_k в статье)
        self.dt = 0.1
        self.create_timer(self.dt, self.loop)

    def _load_truth_map(self, src_dir):
        try:
            base_dir = os.path.join(src_dir, 'maps')
            map_path = os.path.join(base_dir, self.map_file_name)
                
            base_name = os.path.splitext(os.path.basename(map_path))[0]
            meta_path = os.path.join(os.path.dirname(map_path), f"{base_name}_meta.json")

            if os.path.exists(map_path):
                self.raw_dose_map = np.load(map_path)
                self.get_logger().info(f"Loaded ground truth map: {self.raw_dose_map.shape}")
                
                if os.path.exists(meta_path):
                    with open(meta_path, 'r') as f:
                        meta = json.load(f)
                        self.rad_ox = meta.get('ox', self.rad_ox)
                        self.rad_oy = meta.get('oy', self.rad_oy)
                        self.rad_res = meta.get('res', self.rad_res)
            else:
                self.get_logger().error(f"Truth map not found: {map_path}. Cannot log properly!")
                
        except Exception as e:
            self.get_logger().error(f"Error loading map: {e}")

    def loop(self):
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
        dose_rate = 0.0
        
        if 0 <= rad_x < max_x and 0 <= rad_y < max_y:
            dose_rate = float(self.raw_dose_map[rad_y, rad_x])

        current_time = time.time()
        if self.last_time is not None:
            actual_dt = current_time - self.last_time
            # Конвертируем dose_rate (мЗв/ч) в накопленную дозу за dt (мкЗв)
            # 1 мЗв/ч = 1000 мкЗв/ч. Делим на 3600 чтобы получить мкЗв в секунду.
            dose_increment_uSv = (dose_rate * 1000.0 / 3600.0) * actual_dt
            self.total_dose_accumulated += dose_increment_uSv
            
            with open(self.log_file, 'a') as f:
                f.write(f"{current_time:.3f},{rx:.3f},{ry:.3f},{dose_rate:.3f},{self.total_dose_accumulated:.3f}\n")
                
        self.last_time = current_time

def main(args=None):
    rclpy.init(args=args)
    node = GroundTruthLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info(f"Total Accumulated Dose: {node.total_dose_accumulated:.3f} uSv")
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
