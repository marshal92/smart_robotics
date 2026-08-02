#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from nav_msgs.msg import OccupancyGrid
from smart_interfaces.msg import SmartCommand
from rclpy.qos import QoSProfile, QoSDurabilityPolicy
import tf2_ros
import os
import numpy as np
from ament_index_python.packages import get_package_share_directory

class VirtualGeiger(Node):
    def __init__(self):
        super().__init__('virtual_geiger')

        self.pub = self.create_publisher(Float32, '/current_dose_rate', 10)
        self.cmd_sub = self.create_subscription(SmartCommand, '/smart_command', self.cmd_cb, 10)
        
        self.map_info = None
        self.raw_dose_map = None
        self.is_active = True

        try:
            pkg_share = get_package_share_directory('smart_radiation')
            map_path = os.path.join(pkg_share, 'maps', 'radiation_map.npy')
            self.raw_dose_map = np.load(map_path)
            self.get_logger().info(f"Loaded physical dose map: {self.raw_dose_map.shape}")
        except Exception as e:
            self.get_logger().error(f"Error loading radiation_map.npy: {e}")

        map_qos = QoSProfile(depth=1, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(OccupancyGrid, '/radiation_map', self.map_cb, map_qos)

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # 5 Hz update rate for telemetry
        self.create_timer(0.2, self.loop)
        self.get_logger().info("Virtual Geiger Counter started (Simulation Mode).")

    def cmd_cb(self, msg):
        if msg.target_system == 'system':
            cmd = msg.command.lower()
            if cmd == 'rad_on':
                self.is_active = True
                self.get_logger().info("Virtual Geiger: ON")
            elif cmd == 'rad_off':
                self.is_active = False
                self.get_logger().info("Virtual Geiger: OFF")

    def map_cb(self, msg):
        self.map_info = msg.info

    def loop(self):
        if not self.is_active:
            msg = Float32()
            msg.data = 0.0
            self.pub.publish(msg)
            return

        if self.map_info is None or self.raw_dose_map is None:
            return

        try:
            # We look up base_footprint to map
            trans = self.tf_buffer.lookup_transform('map', 'base_footprint', rclpy.time.Time())
            rx = trans.transform.translation.x
            ry = trans.transform.translation.y
        except Exception:
            # Wait for TF
            return

        res = self.map_info.resolution
        ox = self.map_info.origin.position.x
        oy = self.map_info.origin.position.y

        rad_x = int((rx - ox) / res)
        rad_y = int((ry - oy) / res)

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
        rclpy.shutdown()

if __name__ == '__main__':
    main()
