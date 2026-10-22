#!/usr/bin/env python3
"""
Экспериментальный логгер для Раздела 4 (§4.2, Блок 2A):
Запуск по сохранённому графу (холодный старт навигационной подсистемы):
1. Засекает время от запуска до появления первой оценки положения в map (t_init_pose_s, t_init_tf_s).
2. Фиксирует начальную позу (x, y, yaw) и её разброс за первые 5 секунд стояния.
3. Проверяет совмещение первого скана (/scan) с картой (/map): доля лучей, попадающих в занятые ячейки карты.
4. Записывает короткий проезд к целевой точке и сохраняет CSV + паспорт эксперимента.
"""

import os
import csv
import json
import math
import time
import platform
from datetime import datetime

import psutil
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry, OccupancyGrid
from geometry_msgs.msg import PoseWithCovarianceStamped
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener


def quat_to_yaw(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def calc_stats(vals):
    if not vals:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "span": 0.0}
    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / n if n > 1 else 0.0
    return {
        "mean": round(mean, 5),
        "std": round(math.sqrt(var), 5),
        "min": round(min(vals), 5),
        "max": round(max(vals), 5),
        "span": round(max(vals) - min(vals), 5),
    }


class Block2ALogger(Node):
    def __init__(self):
        super().__init__('block2a_logger')

        self.declare_parameter('run_num', 1)
        self.declare_parameter('map_name', 'shelter_012.7')
        self.declare_parameter('rate_hz', 5.0)
        self.declare_parameter('init_window_sec', 5.0)
        self.declare_parameter('notes', '')
        self.declare_parameter('log_dir', '/home/oleksandr/ros2_ws/src/smart_robotics/smart_sandbox/logs')

        self.run_num = int(self.get_parameter('run_num').value)
        self.map_name = str(self.get_parameter('map_name').value)
        self.rate_hz = float(self.get_parameter('rate_hz').value)
        self.init_window_sec = float(self.get_parameter('init_window_sec').value)
        self.notes = str(self.get_parameter('notes').value)
        self.log_dir = str(self.get_parameter('log_dir').value)

        os.makedirs(self.log_dir, exist_ok=True)

        ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_map = self.map_name.replace('/', '_').replace(' ', '_')
        self.run_id = f"block2a_run{self.run_num}_{safe_map}_{ts_str}"
        self.csv_path = os.path.join(self.log_dir, f"{self.run_id}_timeseries.csv")
        self.passport_path = os.path.join(self.log_dir, f"{self.run_id}_passport.json")

        self.t0_wall = time.time()
        self.t_slam_proc_start = None
        self.t_first_pose_topic_wall = None
        self.t_first_map_tf_wall = None
        self.t_first_map_grid_wall = None
        self.t_first_pose_topic = None
        self.t_first_map_tf = None
        self.t_first_map_grid = None
        self.t_first_move = None

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.pose_topic_x = None
        self.pose_topic_y = None
        self.pose_topic_yaw = None

        self.odom_x = 0.0
        self.odom_y = 0.0
        self.v_lin = 0.0
        self.v_ang = 0.0
        self.nav_status = "IDLE"

        self.map_msg = None
        self.last_scan = None
        self.scan_map_match_ratio = None
        self.scan_valid_beams = 0

        # Выборка начальной позы за первые init_window_sec после появления оценки
        self.init_samples_x = []
        self.init_samples_y = []
        self.init_samples_yaw_deg = []

        # Траектория короткого движения
        self.path_length_m = 0.0
        self.prev_map_x = None
        self.prev_map_y = None
        self.final_map_x = 0.0
        self.final_map_y = 0.0
        self.final_map_yaw_deg = 0.0

        scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        self.create_subscription(PoseWithCovarianceStamped, '/pose', self._pose_cb, 10)
        self.create_subscription(Odometry, '/odom', self._odom_cb, 10)
        self.create_subscription(OccupancyGrid, '/map', self._map_cb, 1)
        self.create_subscription(LaserScan, '/scan', self._scan_cb, scan_qos)
        self.create_subscription(String, '/nav_status', self._nav_cb, 10)

        self.csv_file = open(self.csv_path, 'w', newline='', encoding='utf-8')
        self.csv_headers = [
            'elapsed_s',
            'tf_available',
            'pose_topic_available',
            'map_x', 'map_y', 'map_yaw_deg',
            'pose_topic_x', 'pose_topic_y', 'pose_topic_yaw_deg',
            'v_lin', 'v_ang',
            'path_length_m',
            'scan_map_match_ratio',
            'nav_status'
        ]
        self.writer = csv.DictWriter(self.csv_file, fieldnames=self.csv_headers)
        self.writer.writeheader()
        self.csv_file.flush()

        self.rows_written = 0
        self.timer = self.create_timer(1.0 / self.rate_hz, self._tick)

        self.get_logger().info(
            f"[Block2A Logger] Started run #{self.run_num} for map '{self.map_name}'.\n"
            f"  Waiting for first /pose and map->base_footprint TF...\n"
            f"  CSV: {self.csv_path}"
        )

    def _detect_slam_start_time(self):
        if self.t_slam_proc_start is not None:
            return
        for proc in psutil.process_iter(['name', 'cmdline', 'create_time']):
            try:
                cmdline = ' '.join(proc.info.get('cmdline') or [])
                if 'slam_toolbox' in cmdline and ('localization_slam_toolbox_node' in cmdline or 'async_slam_toolbox_node' in cmdline):
                    self.t_slam_proc_start = float(proc.info['create_time'])
                    self.get_logger().info(f"Detected slam_toolbox process start (pid={proc.pid})")
                    return
            except Exception:
                pass

    def _pose_cb(self, msg: PoseWithCovarianceStamped):
        now = time.time()
        if self.t_first_pose_topic is None:
            self._detect_slam_start_time()
            self.t_first_pose_topic_wall = now
            self.t_first_pose_topic = round(now - self.t0_wall, 3)
            self.get_logger().info(f"First /pose received at t = {self.t_first_pose_topic:.3f} s")
        self.pose_topic_x = msg.pose.pose.position.x
        self.pose_topic_y = msg.pose.pose.position.y
        self.pose_topic_yaw = math.degrees(quat_to_yaw(msg.pose.pose.orientation))

    def _odom_cb(self, msg: Odometry):
        self.odom_x = msg.pose.pose.position.x
        self.odom_y = msg.pose.pose.position.y
        self.v_lin = msg.twist.twist.linear.x
        self.v_ang = msg.twist.twist.angular.z
        if self.t_first_move is None and abs(self.v_lin) > 0.03:
            self.t_first_move = round(time.time() - self.t0_wall, 3)

    def _map_cb(self, msg: OccupancyGrid):
        now = time.time()
        if self.t_first_map_grid is None:
            self._detect_slam_start_time()
            self.t_first_map_grid_wall = now
            self.t_first_map_grid = round(now - self.t0_wall, 3)
            self.get_logger().info(
                f"First /map received at t = {self.t_first_map_grid:.3f} s "
                f"({msg.info.width}x{msg.info.height}, res={msg.info.resolution})"
            )
        self.map_msg = msg

    def _scan_cb(self, msg: LaserScan):
        self.last_scan = msg

    def _nav_cb(self, msg: String):
        self.nav_status = msg.data.strip()

    def _compute_scan_map_match(self, rx, ry, ryaw_rad):
        """Оценивает долю лучей /scan, попавших в занятые ячейки /map (в окрестности +-2 ячейки = +-10 см)."""
        if self.map_msg is None or self.last_scan is None:
            return None
        info = self.map_msg.info
        res = info.resolution
        ox = info.origin.position.x
        oy = info.origin.position.y
        w = info.width
        h = info.height
        data = self.map_msg.data

        scan = self.last_scan
        angle = scan.angle_min
        inc = scan.angle_increment
        hits = 0
        valid = 0

        # Учитываем смещение лазера относительно base_footprint (~ -0.12, +0.06)
        lx = rx - 0.12 * math.cos(ryaw_rad) - 0.06 * math.sin(ryaw_rad)
        ly = ry - 0.12 * math.sin(ryaw_rad) + 0.06 * math.cos(ryaw_rad)

        for r in scan.ranges:
            if scan.range_min < r < min(scan.range_max - 0.1, 9.5) and not math.isinf(r) and not math.isnan(r):
                valid += 1
                bx = lx + r * math.cos(ryaw_rad + angle)
                by = ly + r * math.sin(ryaw_rad + angle)
                gx = int((bx - ox) / res)
                gy = int((by - oy) / res)
                matched = False
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        nx, ny = gx + dx, gy + dy
                        if 0 <= nx < w and 0 <= ny < h:
                            if data[ny * w + nx] > 50:
                                matched = True
                                break
                    if matched:
                        break
                if matched:
                    hits += 1
            angle += inc

        self.scan_valid_beams = valid
        if valid == 0:
            return None
        return round(hits / valid, 4)

    def _tick(self):
        now = time.time()
        elapsed = round(now - self.t0_wall, 3)

        tf_ok = 0
        map_x, map_y, map_yaw_deg = 0.0, 0.0, 0.0
        map_yaw_rad = 0.0

        try:
            t = self.tf_buffer.lookup_transform('map', 'base_footprint', rclpy.time.Time())
            tf_ok = 1
            map_x = t.transform.translation.x
            map_y = t.transform.translation.y
            map_yaw_rad = quat_to_yaw(t.transform.rotation)
            map_yaw_deg = math.degrees(map_yaw_rad)

            if self.t_first_map_tf is None:
                self._detect_slam_start_time()
                self.t_first_map_tf_wall = now
                self.t_first_map_tf = elapsed
                from_slam = round(now - self.t_slam_proc_start, 3) if self.t_slam_proc_start else elapsed
                self.get_logger().info(
                    f"First map->base_footprint TF at t = {self.t_first_map_tf:.3f} s "
                    f"(from slam_toolbox start: {from_slam:.3f} s): "
                    f"x={map_x:.4f}, y={map_y:.4f}, yaw={map_yaw_deg:.2f} deg"
                )
        except Exception:
            tf_ok = 0

        if tf_ok:
            self.final_map_x = map_x
            self.final_map_y = map_y
            self.final_map_yaw_deg = map_yaw_deg

            # Собираем начальное окно оценки позы (первые init_window_sec после появления TF, пока робот стоит)
            if self.t_first_map_tf is not None and (elapsed - self.t_first_map_tf) <= self.init_window_sec and self.t_first_move is None:
                self.init_samples_x.append(map_x)
                self.init_samples_y.append(map_y)
                self.init_samples_yaw_deg.append(map_yaw_deg)

            if self.prev_map_x is not None:
                step = math.hypot(map_x - self.prev_map_x, map_y - self.prev_map_y)
                if 0.002 < step < 1.0:
                    self.path_length_m += step
            self.prev_map_x = map_x
            self.prev_map_y = map_y

            if self.scan_map_match_ratio is None or self.rows_written % 5 == 0:
                ratio = self._compute_scan_map_match(map_x, map_y, map_yaw_rad)
                if ratio is not None:
                    self.scan_map_match_ratio = ratio

        row = {
            'elapsed_s': elapsed,
            'tf_available': tf_ok,
            'pose_topic_available': 1 if self.pose_topic_x is not None else 0,
            'map_x': round(map_x, 5) if tf_ok else '',
            'map_y': round(map_y, 5) if tf_ok else '',
            'map_yaw_deg': round(map_yaw_deg, 3) if tf_ok else '',
            'pose_topic_x': round(self.pose_topic_x, 5) if self.pose_topic_x is not None else '',
            'pose_topic_y': round(self.pose_topic_y, 5) if self.pose_topic_y is not None else '',
            'pose_topic_yaw_deg': round(self.pose_topic_yaw, 3) if self.pose_topic_yaw is not None else '',
            'v_lin': round(self.v_lin, 4),
            'v_ang': round(self.v_ang, 4),
            'path_length_m': round(self.path_length_m, 4),
            'scan_map_match_ratio': self.scan_map_match_ratio if self.scan_map_match_ratio is not None else '',
            'nav_status': self.nav_status,
        }
        self.writer.writerow(row)
        self.rows_written += 1
        if self.rows_written % 5 == 0:
            self.csv_file.flush()

    def save_passport(self):
        duration_s = round(time.time() - self.t0_wall, 3)
        t_tf_from_slam = round(self.t_first_map_tf_wall - self.t_slam_proc_start, 3) if (self.t_first_map_tf_wall and self.t_slam_proc_start) else self.t_first_map_tf
        t_pose_from_slam = round(self.t_first_pose_topic_wall - self.t_slam_proc_start, 3) if (self.t_first_pose_topic_wall and self.t_slam_proc_start) else self.t_first_pose_topic
        t_map_from_slam = round(self.t_first_map_grid_wall - self.t_slam_proc_start, 3) if (self.t_first_map_grid_wall and self.t_slam_proc_start) else self.t_first_map_grid
        passport = {
            "experiment": "Chapter 4 - §4.2 Block 2A (Cold Start with Saved Posegraph & Short Goal)",
            "run_id": self.run_id,
            "run_num": self.run_num,
            "timestamp_iso": datetime.now().isoformat(),
            "map_name": self.map_name,
            "hardware": {
                "hostname": platform.node(),
                "processor": platform.processor(),
            },
            "initialization_metrics": {
                "t_from_slam_start_to_first_map_tf_s": t_tf_from_slam,
                "t_from_slam_start_to_first_pose_s": t_pose_from_slam,
                "t_from_slam_start_to_first_map_grid_s": t_map_from_slam,
                "t_first_map_tf_s": self.t_first_map_tf,
                "t_first_pose_topic_s": self.t_first_pose_topic,
                "t_first_map_grid_s": self.t_first_map_grid,
                "init_window_sec": self.init_window_sec,
                "init_samples_count": len(self.init_samples_x),
                "initial_pose_x_m": calc_stats(self.init_samples_x),
                "initial_pose_y_m": calc_stats(self.init_samples_y),
                "initial_pose_yaw_deg": calc_stats(self.init_samples_yaw_deg),
                "scan_map_match_ratio": self.scan_map_match_ratio,
                "scan_valid_beams": self.scan_valid_beams,
            },
            "short_goal_metrics": {
                "t_first_move_s": self.t_first_move,
                "total_duration_s": duration_s,
                "path_length_m": round(self.path_length_m, 4),
                "final_pose": {
                    "x_m": round(self.final_map_x, 4),
                    "y_m": round(self.final_map_y, 4),
                    "yaw_deg": round(self.final_map_yaw_deg, 2),
                },
                "last_nav_status": self.nav_status,
            },
            "notes": self.notes,
            "csv_file": self.csv_path,
        }
        with open(self.passport_path, 'w', encoding='utf-8') as f:
            json.dump(passport, f, ensure_ascii=False, indent=2)
        self.csv_file.flush()
        self.csv_file.close()
        self.get_logger().info(f"[Block2A Logger] Saved passport: {self.passport_path}")


def main(args=None):
    rclpy.init(args=args)
    node = Block2ALogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.save_passport()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
