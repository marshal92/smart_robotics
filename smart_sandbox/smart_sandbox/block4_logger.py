#!/usr/bin/env python3
"""
Экспериментальный логгер для Раздела 4 (§4.2, Блок 4):
3D-лидар и пространственная редукция на рельефе (сравнение вариантов обработки:
со стабилизацией в base_stabilized vs без компенсации крена/тангажа в наклонённой системе корпуса).

Согласно Chapter4_plan_v0773.md (§4.2, Блок 4):
- Записывает временной ряд (10 Гц) в CSV: крен, тангаж, скорости, координаты, дальности /scan, статус.
- Формирует расширенный JSON-паспорт эксперимента со всеми калибровочными параметрами:
  высота установки лидара, диапазон среза основного препятствия, параметры низкопрофильного
  фильтра микрорельефа/ступенек, маска корпуса робота, аппаратный снимок и интегральные метрики.
"""

import os
import csv
import json
import math
import time
import platform
import subprocess
from datetime import datetime

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu, LaserScan
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener


def quat_to_rpy_deg(q):
    # Roll (x-axis rotation)
    sinr_cosp = 2.0 * (q.w * q.x + q.y * q.z)
    cosr_cosp = 1.0 - 2.0 * (q.x * q.x + q.y * q.y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2.0 * (q.w * q.y - q.z * q.x)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def calc_stats(vals):
    if not vals:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0, "max_abs": 0.0}
    s = sorted(vals)
    n = len(s)
    mean = sum(s) / n
    var = sum((x - mean) ** 2 for x in s) / n if n > 1 else 0.0
    return {
        "mean": round(mean, 4),
        "std": round(math.sqrt(var), 4),
        "min": round(s[0], 4),
        "p50": round(percentile(s, 50), 4),
        "p95": round(percentile(s, 95), 4),
        "max": round(s[-1], 4),
        "max_abs": round(max(abs(x) for x in s), 4),
    }


class Block4Logger(Node):
    def __init__(self):
        super().__init__('block4_logger')

        self.declare_parameter('variant', 'stabilized')       # 'stabilized' или 'unstabilized'
        self.declare_parameter('target_frame', 'base_stabilized')
        self.declare_parameter('lidar_mount_height', 0.30)    # Высота лидара над землёй (м)
        self.declare_parameter('min_height', 0.30)            # Нижняя граница основного среза (м)
        self.declare_parameter('max_height', 0.80)            # Верхняя граница основного среза (м)
        self.declare_parameter('low_min_height', 0.10)        # Нижняя граница детектора ступенек (м)
        self.declare_parameter('low_max_height', 0.30)        # Верхняя граница детектора ступенек (м)
        self.declare_parameter('min_step_height', 0.09)       # Порог высоты ступеньки/бордюра (м)
        self.declare_parameter('max_slope_deg', 38.0)         # Максимальный уклон преодоления рельефа (град)
        self.declare_parameter('despeckle_min_cluster', 3)    # Минимальное число лучей в кластере для фильтра шума
        self.declare_parameter('mask_length_x', 0.70)         # Длина маски шасси робота (м)
        self.declare_parameter('mask_width_y', 0.56)          # Ширина маски шасси робота (м)
        self.declare_parameter('rate_hz', 10.0)               # Частота логирования временного ряда
        self.declare_parameter('world', 'shelter_zero.sdf')   # Текущий мир симуляции
        self.declare_parameter('notes', '')
        self.declare_parameter('log_dir', '/home/oleksandr/ros2_ws/src/smart_robotics/smart_sandbox/logs')

        self.variant = str(self.get_parameter('variant').value)
        self.target_frame = str(self.get_parameter('target_frame').value)
        self.lidar_mount_height = float(self.get_parameter('lidar_mount_height').value)
        self.min_height = float(self.get_parameter('min_height').value)
        self.max_height = float(self.get_parameter('max_height').value)
        self.low_min_height = float(self.get_parameter('low_min_height').value)
        self.low_max_height = float(self.get_parameter('low_max_height').value)
        self.min_step_height = float(self.get_parameter('min_step_height').value)
        self.max_slope_deg = float(self.get_parameter('max_slope_deg').value)
        self.despeckle_min_cluster = int(self.get_parameter('despeckle_min_cluster').value)
        self.mask_length_x = float(self.get_parameter('mask_length_x').value)
        self.mask_width_y = float(self.get_parameter('mask_width_y').value)
        self.rate_hz = float(self.get_parameter('rate_hz').value)
        self.world = str(self.get_parameter('world').value)
        self.notes = str(self.get_parameter('notes').value)
        self.log_dir = str(self.get_parameter('log_dir').value)

        os.makedirs(self.log_dir, exist_ok=True)

        ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.run_id = f"block4_{self.variant}_{ts_str}"
        self.csv_path = os.path.join(self.log_dir, f"{self.run_id}_timeseries.csv")
        self.passport_path = os.path.join(self.log_dir, f"{self.run_id}_passport.json")

        self.t0_wall = time.time()
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # Показатели кинематики и ориентации
        self.odom_x = 0.0
        self.odom_y = 0.0
        self.odom_z = 0.0
        self.roll_deg = 0.0
        self.pitch_deg = 0.0
        self.yaw_deg = 0.0
        self.tilt_deg = 0.0
        self.v_lin = 0.0
        self.v_ang = 0.0

        # Параметры текущего LaserScan (/scan после stabilized_frame_publisher)
        self.scan_min_range = None
        self.scan_front_min_range = None
        self.scan_close_beams_lt_1_5m = 0
        self.scan_valid_beams = 0

        self.nav_status = "IDLE"
        self.section_completed = False
        self.path_length_m = 0.0
        self.prev_x = None
        self.prev_y = None

        # Массивы и счётчики для расширенной статистики
        self.hist_roll = []
        self.hist_pitch = []
        self.hist_tilt = []
        self.hist_v_lin = []
        self.hist_front_min = []
        self.hist_close_beams = []

        self.ticks_active_move = 0
        self.ticks_phantom_blocked = 0    # Близкое препятствие спереди (<1.2м) во время движения
        self.ticks_hesitation_stuck = 0   # Статус движения есть, но скорость робота упала (<0.02 м/с)

        # Подписка на топики
        scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        self.create_subscription(Odometry, '/odom', self._odom_cb, 20)
        self.create_subscription(Imu, '/imu/data', self._imu_cb, 20)
        self.create_subscription(LaserScan, '/scan', self._scan_cb, scan_qos)
        self.create_subscription(String, '/nav_status', self._nav_cb, 10)

        self.csv_file = open(self.csv_path, 'w', newline='', encoding='utf-8')
        self.csv_headers = [
            'elapsed_s',
            'odom_x', 'odom_y', 'odom_z',
            'map_x', 'map_y',
            'roll_deg', 'pitch_deg', 'yaw_deg', 'tilt_deg',
            'v_lin_mps', 'v_ang_rps',
            'path_length_m',
            'scan_min_range_m', 'scan_front_min_range_m',
            'scan_close_beams_lt_1_5m', 'scan_valid_beams',
            'nav_status'
        ]
        self.writer = csv.DictWriter(self.csv_file, fieldnames=self.csv_headers)
        self.writer.writeheader()
        self.csv_file.flush()

        self.rows_written = 0
        self.timer = self.create_timer(1.0 / self.rate_hz, self._tick)

        self.get_logger().info(
            f"[Block4 Logger] Started terrain 3D-LiDAR logger.\n"
            f"  Variant: '{self.variant}', Frame: '{self.target_frame}'\n"
            f"  Slice: [{self.min_height:.2f}, {self.max_height:.2f}] m, Step filter: [{self.low_min_height:.2f}, {self.low_max_height:.2f}] m, min_step: {self.min_step_height:.2f} m\n"
            f"  CSV: {self.csv_path}\n"
            f"  Passport: {self.passport_path}"
        )

    def _odom_cb(self, msg: Odometry):
        self.odom_x = msg.pose.pose.position.x
        self.odom_y = msg.pose.pose.position.y
        self.odom_z = msg.pose.pose.position.z
        self.v_lin = msg.twist.twist.linear.x
        self.v_ang = msg.twist.twist.angular.z

        r, p, y = quat_to_rpy_deg(msg.pose.pose.orientation)
        self.yaw_deg = y
        # Если в /odom есть реальный 3D-наклон (не плоская 2D-одометрия), обновляем
        if abs(r) > 0.02 or abs(p) > 0.02:
            self.roll_deg = r
            self.pitch_deg = p
            self.tilt_deg = math.hypot(r, p)

        if self.prev_x is not None:
            step = math.hypot(self.odom_x - self.prev_x, self.odom_y - self.prev_y)
            if 0.001 < step < 0.5:
                self.path_length_m += step
        self.prev_x = self.odom_x
        self.prev_y = self.odom_y

    def _imu_cb(self, msg: Imu):
        # IMU гарантированно несёт физический крен и тангаж корпуса танка
        r, p, _ = quat_to_rpy_deg(msg.orientation)
        self.roll_deg = r
        self.pitch_deg = p
        self.tilt_deg = math.hypot(r, p)

    def _scan_cb(self, msg: LaserScan):
        valid = []
        front_valid = []
        close_cnt = 0
        angle = msg.angle_min
        inc = msg.angle_increment

        for r in msg.ranges:
            if msg.range_min < r < msg.range_max and not math.isinf(r) and not math.isnan(r):
                valid.append(r)
                if r < 1.5:
                    close_cnt += 1
                # Сектор +-30 градусов спереди по курсу
                if abs(angle) <= math.radians(30.0):
                    front_valid.append(r)
            angle += inc

        self.scan_valid_beams = len(valid)
        self.scan_close_beams_lt_1_5m = close_cnt
        self.scan_min_range = round(min(valid), 4) if valid else None
        self.scan_front_min_range = round(min(front_valid), 4) if front_valid else None

    def _nav_cb(self, msg: String):
        self.nav_status = msg.data.strip()
        if any(k in self.nav_status.lower() for k in ('succeeded', 'completed', 'reached')):
            if self.path_length_m > 0.5:
                self.section_completed = True

    def _get_ros_node_params_dump(self, node_name):
        try:
            r = subprocess.run(
                ['ros2', 'param', 'dump', node_name],
                capture_output=True, text=True, timeout=2.5
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        return "unavailable"

    def _tick(self):
        elapsed = round(time.time() - self.t0_wall, 3)

        map_x, map_y = '', ''
        try:
            t = self.tf_buffer.lookup_transform('map', 'base_footprint', rclpy.time.Time())
            map_x = round(t.transform.translation.x, 4)
            map_y = round(t.transform.translation.y, 4)
        except Exception:
            pass

        self.hist_roll.append(self.roll_deg)
        self.hist_pitch.append(self.pitch_deg)
        self.hist_tilt.append(self.tilt_deg)
        self.hist_v_lin.append(self.v_lin)
        self.hist_close_beams.append(self.scan_close_beams_lt_1_5m)
        if self.scan_front_min_range is not None:
            self.hist_front_min.append(self.scan_front_min_range)

        # Мониторинг мобильности и ложных препятствий
        is_active_nav = any(k in self.nav_status.upper() for k in ('MOV', 'EXEC', 'ACTIVE', 'GOAL', 'RUN'))
        if is_active_nav or abs(self.v_lin) > 0.02:
            self.ticks_active_move += 1
            if self.scan_front_min_range is not None and self.scan_front_min_range < 1.20:
                self.ticks_phantom_blocked += 1
            if abs(self.v_lin) < 0.02:
                self.ticks_hesitation_stuck += 1

        row = {
            'elapsed_s': elapsed,
            'odom_x': round(self.odom_x, 4),
            'odom_y': round(self.odom_y, 4),
            'odom_z': round(self.odom_z, 4),
            'map_x': map_x,
            'map_y': map_y,
            'roll_deg': round(self.roll_deg, 3),
            'pitch_deg': round(self.pitch_deg, 3),
            'yaw_deg': round(self.yaw_deg, 3),
            'tilt_deg': round(self.tilt_deg, 3),
            'v_lin_mps': round(self.v_lin, 4),
            'v_ang_rps': round(self.v_ang, 4),
            'path_length_m': round(self.path_length_m, 4),
            'scan_min_range_m': self.scan_min_range if self.scan_min_range is not None else '',
            'scan_front_min_range_m': self.scan_front_min_range if self.scan_front_min_range is not None else '',
            'scan_close_beams_lt_1_5m': self.scan_close_beams_lt_1_5m,
            'scan_valid_beams': self.scan_valid_beams,
            'nav_status': self.nav_status,
        }
        self.writer.writerow(row)
        self.rows_written += 1
        if self.rows_written % 10 == 0:
            self.csv_file.flush()

    def save_passport(self):
        duration_s = round(time.time() - self.t0_wall, 3)
        mean_speed = round(self.path_length_m / duration_s, 4) if duration_s > 0 else 0.0
        phantom_ratio = round(self.ticks_phantom_blocked / self.ticks_active_move, 4) if self.ticks_active_move > 0 else 0.0
        stuck_ratio = round(self.ticks_hesitation_stuck / self.ticks_active_move, 4) if self.ticks_active_move > 0 else 0.0
        mobility_fraction = round(1.0 - stuck_ratio, 4)

        passport = {
            "experiment": "Chapter 4 - §4.2 Block 4 (3D LiDAR Spatial Reduction on Terrain)",
            "run_id": self.run_id,
            "timestamp_iso": datetime.now().isoformat(),
            "variant": self.variant,
            "world": self.world,
            "hardware_and_chassis": {
                "hostname": platform.node(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count(),
                "lidar_mount_height_m": self.lidar_mount_height,
                "chassis_dimensions_m": {
                    "length": self.mask_length_x,
                    "width": self.mask_width_y,
                    "height": 0.35,
                },
                "robot_exclusion_mask_m": {
                    "x_range": [-round(self.mask_length_x / 2.0, 3), round(self.mask_length_x / 2.0, 3)],
                    "y_range": [-round(self.mask_width_y / 2.0, 3), round(self.mask_width_y / 2.0, 3)],
                },
            },
            "processing_config": {
                "sensor": "3D GPU LiDAR (16 channels, vertical FOV [-15°, +15°], range 0.30-20.0m)",
                "target_frame": self.target_frame,
                "roll_pitch_compensation": (self.variant == 'stabilized' or self.target_frame == 'base_stabilized'),
                "main_slice": {
                    "min_height_m": self.min_height,
                    "max_height_m": self.max_height,
                    "thickness_m": round(self.max_height - self.min_height, 3),
                },
                "low_obstacle_filter": {
                    "enabled": True,
                    "low_min_height_m": self.low_min_height,
                    "low_max_height_m": self.low_max_height,
                    "min_step_height_m": self.min_step_height,
                    "max_traversable_slope_deg": self.max_slope_deg,
                    "max_step_eval_range_m": 3.20,
                    "despeckle_min_cluster_bins": self.despeckle_min_cluster,
                    "despeckle_max_bin_diff_m": 0.18,
                },
                "scan_output": {
                    "num_beams": 720,
                    "angular_increment_deg": 0.5,
                    "rate_hz": 10.0,
                    "qos": "RELIABLE (depth 10, compatible with Nav2 costmap & SLAM)",
                },
            },
            "ros_parameters_snapshot": {
                "stabilized_frame_publisher": self._get_ros_node_params_dump('/stabilized_frame_publisher'),
            },
            "summary_metrics": {
                "duration_s": duration_s,
                "path_length_m": round(self.path_length_m, 4),
                "mean_traversal_speed_mps": mean_speed,
                "section_completed": self.section_completed,
                "last_nav_status": self.nav_status,
                "phantom_obstacle_ratio": phantom_ratio,
                "stuck_hesitation_ratio": stuck_ratio,
                "mobility_fraction": mobility_fraction,
                "roll_deg": calc_stats(self.hist_roll),
                "pitch_deg": calc_stats(self.hist_pitch),
                "total_tilt_deg": calc_stats(self.hist_tilt),
                "linear_velocity_mps": calc_stats(self.hist_v_lin),
                "front_scan_min_range_m": calc_stats(self.hist_front_min),
                "close_beams_lt_1_5m": calc_stats(self.hist_close_beams),
            },
            "notes": self.notes,
            "csv_file": self.csv_path,
        }
        with open(self.passport_path, 'w', encoding='utf-8') as f:
            json.dump(passport, f, ensure_ascii=False, indent=2)
        self.csv_file.flush()
        self.csv_file.close()
        self.get_logger().info(f"[Block4 Logger] Saved passport: {self.passport_path}")


def main(args=None):
    rclpy.init(args=args)
    node = Block4Logger()
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
