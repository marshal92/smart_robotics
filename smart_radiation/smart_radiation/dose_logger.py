#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.qos import QoSProfile, QoSDurabilityPolicy
import tf2_ros
import time
import csv
import math
import os
import numpy as np
from datetime import datetime
from ament_index_python.packages import get_package_share_directory

class TelemetryLogger(Node):
    def __init__(self):
        super().__init__('telemetry_logger')

        self.update_rate_hz = 10.0      
        self.dt_hours = (1.0 / self.update_rate_hz) / 3600.0  

        self.map_info = None
        self.accumulated_dose_msv = 0.0     
        self.current_dose_rate_msv = 0.0
        self.total_distance = 0.0
        self.current_speed = 0.0
        self.last_x = None
        self.last_y = None
        self.start_time = time.time()

        try:
            pkg_share = get_package_share_directory('smart_radiation')
            map_path = os.path.join(pkg_share, 'maps', 'radiation_map.npy')
            self.raw_dose_map = np.load(map_path)
            self.get_logger().info(f"Physical map loaded for logger: {self.raw_dose_map.shape}")
        except Exception as e:
            self.get_logger().error(f"Error loading radiation_map.npy: {e}")
            self.raw_dose_map = None

        map_qos = QoSProfile(depth=1, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(OccupancyGrid, '/radiation_map', self.map_cb, map_qos)
        self.create_subscription(Odometry, '/odom/unfiltered', self.odom_cb, 10)

        # TF Listener
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # CSV SETTINGS
        self.log_dir = os.path.expanduser('~/.ros/smart_data/telemetry')
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_file = open(os.path.join(self.log_dir, f'dose_log_{timestamp}.csv'), 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(['Time(s)', 'X', 'Y', 'Speed(m/s)', 'DoseRate(mSv/h)', 'AccumDose(mSv)', 'Distance(m)'])

        self.create_timer(1.0 / self.update_rate_hz, self.loop)
        self.create_timer(5.0, self.print_stats)

    def map_cb(self, msg):
        self.map_info = msg.info

    def odom_cb(self, msg):
        vx = msg.twist.twist.linear.x
        vy = msg.twist.twist.linear.y
        self.current_speed = math.sqrt(vx**2 + vy**2)

    def loop(self):
        if self.map_info is None or self.raw_dose_map is None:
            return

        try:
            trans = self.tf_buffer.lookup_transform('map', 'base_footprint', rclpy.time.Time())
            rx = trans.transform.translation.x
            ry = trans.transform.translation.y
        except Exception:
            return

        if self.last_x is not None:
            dist = math.sqrt((rx - self.last_x)**2 + (ry - self.last_y)**2)
            if dist < 1.0: 
                self.total_distance += dist
        self.last_x = rx
        self.last_y = ry

        res = self.map_info.resolution
        ox = self.map_info.origin.position.x
        oy = self.map_info.origin.position.y

        rad_x = int((rx - ox) / res)
        rad_y = int((ry - oy) / res)

        max_y, max_x = self.raw_dose_map.shape
        if 0 <= rad_x < max_x and 0 <= rad_y < max_y:
            self.current_dose_rate_msv = float(self.raw_dose_map[rad_y, rad_x])
        else:
            self.current_dose_rate_msv = 0.0

        self.accumulated_dose_msv += self.current_dose_rate_msv * self.dt_hours

        elapsed_time = time.time() - self.start_time
        self.csv_writer.writerow([
            round(elapsed_time, 2), round(rx, 3), round(ry, 3), 
            round(self.current_speed, 3), round(self.current_dose_rate_msv, 3), 
            round(self.accumulated_dose_msv, 5), round(self.total_distance, 3)
        ])

    def print_stats(self):
        if self.last_x is None: return
        elapsed_time = time.time() - self.start_time
        self.get_logger().info(
            f"T: {elapsed_time:.1f}s | Dist: {self.total_distance:.2f}m | Speed: {self.current_speed:.2f} m/s\n"
            f"  -> Dose Rate: {self.current_dose_rate_msv:.1f} mSv/h | Accum: {self.accumulated_dose_msv:.4f} mSv"
        )

def main(args=None):
    rclpy.init(args=args)
    node = TelemetryLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.csv_file.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()