#!/usr/bin/env python3
"""
Экспериментальный логгер для Раздела 4 (§4.2, Блок 2B):
Сравнение режимов SLAM Toolbox (localization / lifelong vs continued mapping)
при многократном прохождении замкнутого маршрута.

Записывает в пакет smart_sandbox/logs/:
1. <run_id>_timeseries.csv  (~300-600 КБ за 30 минут при 1-2 Гц)
2. <run_id>_passport.json   (паспорт теста: режим SLAM, карта, параметры, железо + итоговая сводка)
"""

import os
import sys
import csv
import json
import math
import time
import platform
import subprocess
from datetime import datetime

import psutil
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry, OccupancyGrid
from std_msgs.msg import String
from visualization_msgs.msg import MarkerArray, Marker
from tf2_ros import Buffer, TransformListener


def quat_to_yaw(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


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
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    s = sorted(vals)
    n = len(s)
    mean = sum(s) / n
    var = sum((x - mean) ** 2 for x in s) / n if n > 1 else 0.0
    return {
        "mean": round(mean, 3),
        "std": round(math.sqrt(var), 3),
        "min": round(s[0], 3),
        "p50": round(percentile(s, 50), 3),
        "p95": round(percentile(s, 95), 3),
        "max": round(s[-1], 3),
    }


class Block2BLogger(Node):
    def __init__(self):
        super().__init__('block2b_logger')

        # Параметры запуска
        self.declare_parameter('mode_label', 'auto')     # 'localization', 'mapping' или 'auto'
        self.declare_parameter('map_name', 'shelter_012.7')
        self.declare_parameter('rate_hz', 1.0)           # 1 Гц = 1800 строк за 30 минут (~320 КБ)
        self.declare_parameter('notes', '')
        self.declare_parameter('log_dir', '/home/oleksandr/ros2_ws/src/smart_robotics/smart_sandbox/logs')

        self.mode_label = self.get_parameter('mode_label').value
        self.map_name = self.get_parameter('map_name').value
        self.rate_hz = float(self.get_parameter('rate_hz').value)
        self.notes = self.get_parameter('notes').value
        self.log_dir = self.get_parameter('log_dir').value

        os.makedirs(self.log_dir, exist_ok=True)

        # Автоопределение процесса SLAM и его режима
        self.tracked_procs = {}
        self.detected_slam_exec = "unknown"
        self._refresh_processes(init_cpu=True)

        if self.mode_label == 'auto':
            if 'localization' in self.detected_slam_exec:
                self.mode_label = 'localization'
            elif 'async' in self.detected_slam_exec or 'sync' in self.detected_slam_exec:
                self.mode_label = 'mapping'
            else:
                self.mode_label = 'unknown_mode'

        ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_map = self.map_name.replace('/', '_').replace(' ', '_')
        self.run_id = f"block2b_{self.mode_label}_{safe_map}_{ts_str}"
        self.csv_path = os.path.join(self.log_dir, f"{self.run_id}_timeseries.csv")
        self.passport_path = os.path.join(self.log_dir, f"{self.run_id}_passport.json")

        # TF и топики
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.odom_x = 0.0
        self.odom_y = 0.0
        self.odom_yaw = 0.0
        self.v_lin = 0.0
        self.v_ang = 0.0

        self.nav_status = "UNKNOWN"
        self.fsm_status = "UNKNOWN"

        # Метрики графа поз SLAM Toolbox (/slam_toolbox/graph_visualization)
        self.graph_nodes = 0
        self.graph_edges = 0
        self.graph_msg_count = 0

        # Метрики карты (/map) — читаем только метаданные и число свободных/занятых ячеек при обновлении
        self.map_width = 0
        self.map_height = 0
        self.map_res = 0.05
        self.map_free_cells = 0
        self.map_occ_cells = 0
        self.map_updates_count = 0

        # Накопление пути и статистики для паспорта
        self.start_wall_time = time.time()
        self.prev_map_x = None
        self.prev_map_y = None
        self.total_distance_m = 0.0
        self.rows_written = 0

        self.hist_slam_cpu = []
        self.hist_slam_rss = []
        self.hist_ctrl_cpu = []
        self.hist_ctrl_rss = []
        self.hist_plan_cpu = []
        self.hist_plan_rss = []
        self.hist_nav2_cpu = []
        self.hist_nav2_rss = []
        self.graph_nodes_start = None
        self.graph_edges_start = None

        # Подписки
        self.create_subscription(Odometry, '/odom', self._odom_cb, 10)
        self.create_subscription(String, '/nav_status', self._nav_status_cb, 10)
        self.create_subscription(String, '/fsm_status', self._fsm_status_cb, 10)
        self.create_subscription(MarkerArray, '/slam_toolbox/graph_visualization', self._graph_cb, 10)
        self.create_subscription(OccupancyGrid, '/map', self._map_cb, 1)

        # Открываем CSV и пишем заголовок
        self.csv_file = open(self.csv_path, mode='w', newline='', encoding='utf-8')
        self.csv_fields = [
            'elapsed_s',
            'timestamp',
            'sim_time_s',
            'mode_label',
            'nav_status',
            'fsm_status',
            # Траектория в map (TF map -> base_footprint)
            'map_x',
            'map_y',
            'map_yaw',
            'total_dist_m',
            # Одометрия и скорости
            'odom_x',
            'odom_y',
            'odom_yaw',
            'v_lin',
            'v_ang',
            # Поправка SLAM (TF map -> odom)
            'map_odom_dx',
            'map_odom_dy',
            'map_odom_dyaw',
            # Граф поз SLAM и размер карты
            'graph_nodes',
            'graph_edges',
            'map_width',
            'map_height',
            'map_free_cells',
            'map_occ_cells',
            'map_updates',
            # Производительность узлов (CPU % одного ядра и память RSS МБ)
            'slam_cpu_pct',
            'slam_rss_mb',
            'controller_cpu_pct',
            'controller_rss_mb',
            'planner_cpu_pct',
            'planner_rss_mb',
            'bt_nav_cpu_pct',
            'bt_nav_rss_mb',
            'nav2_total_cpu_pct',
            'nav2_total_rss_mb',
            'sys_cpu_pct',
            'sys_ram_used_mb',
        ]
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=self.csv_fields)
        self.csv_writer.writeheader()
        self.csv_file.flush()

        # Сохраняем стартовый паспорт теста
        self.passport_data = self._build_initial_passport()
        self._save_passport()

        period = 1.0 / max(0.1, self.rate_hz)
        self.timer = self.create_timer(period, self._log_tick)

        self.get_logger().info("==========================================================")
        self.get_logger().info(f"[Block 2B Logger] STARTED: {self.run_id}")
        self.get_logger().info(f"  SLAM Mode : {self.mode_label} (exec: {self.detected_slam_exec})")
        self.get_logger().info(f"  Map Name  : {self.map_name}")
        self.get_logger().info(f"  CSV File  : {self.csv_path}")
        self.get_logger().info(f"  Passport  : {self.passport_path}")
        self.get_logger().info("==========================================================")

    def _odom_cb(self, msg: Odometry):
        self.odom_x = msg.pose.pose.position.x
        self.odom_y = msg.pose.pose.position.y
        self.odom_yaw = quat_to_yaw(msg.pose.pose.orientation)
        self.v_lin = msg.twist.twist.linear.x
        self.v_ang = msg.twist.twist.angular.z

    def _nav_status_cb(self, msg: String):
        self.nav_status = msg.data

    def _fsm_status_cb(self, msg: String):
        self.fsm_status = msg.data

    def _graph_cb(self, msg: MarkerArray):
        nodes = 0
        edges = 0
        for m in msg.markers:
            # В slam_toolbox вершины графа публикуются как SPHERE / SPHERE_LIST, а рёбра как LINE_LIST
            if m.type == Marker.LINE_LIST:
                edges += len(m.points) // 2
            elif m.type == Marker.SPHERE_LIST:
                nodes += len(m.points)
            elif m.type == Marker.SPHERE:
                nodes += 1
        if nodes > 0 or edges > 0:
            self.graph_nodes = nodes
            self.graph_edges = edges
            self.graph_msg_count += 1
            if self.graph_nodes_start is None and nodes > 0:
                self.graph_nodes_start = nodes
                self.graph_edges_start = edges

    def _map_cb(self, msg: OccupancyGrid):
        self.map_width = msg.info.width
        self.map_height = msg.info.height
        self.map_res = msg.info.resolution
        data = msg.data
        # Быстрый подсчёт свободных (0) и занятых (>50) ячеек
        self.map_free_cells = data.count(0)
        self.map_occ_cells = sum(1 for v in data if v > 50)
        self.map_updates_count += 1

    def _lookup_tf_2d(self, target_frame, source_frame):
        try:
            t = self.tf_buffer.lookup_transform(target_frame, source_frame, rclpy.time.Time())
            x = t.transform.translation.x
            y = t.transform.translation.y
            yaw = quat_to_yaw(t.transform.rotation)
            return x, y, yaw
        except Exception:
            return None, None, None

    def _refresh_processes(self, init_cpu=False):
        """Находит процессы SLAM Toolbox и Nav2 по имени исполняемого файла."""
        target_Map = {
            'slam_toolbox': ('async_slam_toolbox_node', 'localization_slam_toolbox_node', 'sync_slam_toolbox_node', 'lifelong_slam_toolbox_node'),
            'controller_server': ('controller_server',),
            'planner_server': ('planner_server',),
            'bt_navigator': ('bt_navigator',),
            'behavior_server': ('behavior_server',),
            'smoother_server': ('smoother_server',),
            'velocity_smoother': ('velocity_smoother',),
            'collision_monitor': ('collision_monitor',),
            'waypoint_follower': ('waypoint_follower',),
            'route_server': ('route_server',),
        }
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if not cmdline:
                    continue
                exe_base = os.path.basename(cmdline[0])
                for key, names in target_Map.items():
                    if exe_base in names:
                        if key not in self.tracked_procs or self.tracked_procs[key].pid != proc.pid:
                            if init_cpu:
                                proc.cpu_percent(interval=None)
                            self.tracked_procs[key] = proc
                            if key == 'slam_toolbox':
                                self.detected_slam_exec = exe_base
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def _sample_proc_metrics(self):
        # Периодически проверяем, не перезапустились ли процессы
        if self.rows_written % 5 == 0:
            self._refresh_processes(init_cpu=False)

        metrics = {}
        nav2_keys = (
            'controller_server', 'planner_server', 'bt_navigator',
            'behavior_server', 'smoother_server', 'velocity_smoother',
            'collision_monitor', 'waypoint_follower', 'route_server'
        )
        nav2_cpu = 0.0
        nav2_rss = 0.0

        for key in ('slam_toolbox',) + nav2_keys:
            proc = self.tracked_procs.get(key)
            cpu_val = 0.0
            rss_val = 0.0
            if proc is not None:
                try:
                    cpu_val = proc.cpu_percent(interval=None)
                    rss_val = proc.memory_info().rss / (1024.0 * 1024.0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.tracked_procs.pop(key, None)
            metrics[f"{key}_cpu"] = round(cpu_val, 2)
            metrics[f"{key}_rss"] = round(rss_val, 2)
            if key in nav2_keys:
                nav2_cpu += cpu_val
                nav2_rss += rss_val

        metrics['nav2_total_cpu'] = round(nav2_cpu, 2)
        metrics['nav2_total_rss'] = round(nav2_rss, 2)
        return metrics

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

    def _build_initial_passport(self):
        vm = psutil.virtual_memory()
        proc_info = {}
        for k, p in self.tracked_procs.items():
            try:
                proc_info[k] = {
                    "pid": p.pid,
                    "exe": os.path.basename(p.cmdline()[0]) if p.cmdline() else p.name(),
                    "cmdline": " ".join(p.cmdline())
                }
            except Exception:
                pass

        return {
            "experiment": "Chapter 4 - Section 4.2 Block 2B (SLAM Localization vs Continued Mapping)",
            "run_id": self.run_id,
            "start_time_iso": datetime.now().isoformat(),
            "mode_label": self.mode_label,
            "detected_slam_executable": self.detected_slam_exec,
            "map_name": self.map_name,
            "sample_rate_hz": self.rate_hz,
            "notes": self.notes,
            "files": {
                "csv_timeseries": self.csv_path,
                "passport_json": self.passport_path,
            },
            "hardware_and_os": {
                "hostname": platform.node(),
                "os": f"{platform.system()} {platform.release()}",
                "processor": platform.processor(),
                "cpu_physical_cores": psutil.cpu_count(logical=False),
                "cpu_logical_cores": psutil.cpu_count(logical=True),
                "ram_total_gb": round(vm.total / (1024.0 ** 3), 2),
            },
            "tracked_processes_at_start": proc_info,
            "ros_parameters_snapshot": {
                "slam_toolbox": self._get_ros_node_params_dump('/slam_toolbox'),
            },
            "summary": "In progress..."
        }

    def _save_passport(self):
        try:
            with open(self.passport_path, 'w', encoding='utf-8') as f:
                json.dump(self.passport_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.get_logger().error(f"Failed to write passport: {e}")

    def _log_tick(self):
        now_wall = time.time()
        elapsed = now_wall - self.start_wall_time
        sim_time_s = self.get_clock().now().nanoseconds / 1e9

        # Позиция робота в карте (map -> base_footprint / base_link)
        map_x, map_y, map_yaw = self._lookup_tf_2d('map', 'base_footprint')
        if map_x is None:
            map_x, map_y, map_yaw = self._lookup_tf_2d('map', 'base_link')

        if map_x is not None and map_y is not None:
            if self.prev_map_x is not None:
                step_d = math.hypot(map_x - self.prev_map_x, map_y - self.prev_map_y)
                # Отсекаем телепортации > 2.0 м за тик
                if step_d < 2.0:
                    self.total_distance_m += step_d
            self.prev_map_x = map_x
            self.prev_map_y = map_y

        # Поправка SLAM (map -> odom)
        mo_x, mo_y, mo_yaw = self._lookup_tf_2d('map', 'odom')

        # Метрики CPU / RAM
        pm = self._sample_proc_metrics()
        sys_cpu = psutil.cpu_percent(interval=None)
        sys_ram_mb = psutil.virtual_memory().used / (1024.0 * 1024.0)

        if pm['slam_toolbox_cpu'] > 0.0 or pm['slam_toolbox_rss'] > 0.0:
            self.hist_slam_cpu.append(pm['slam_toolbox_cpu'])
            self.hist_slam_rss.append(pm['slam_toolbox_rss'])
        if pm['controller_server_cpu'] > 0.0 or pm['controller_server_rss'] > 0.0:
            self.hist_ctrl_cpu.append(pm['controller_server_cpu'])
            self.hist_ctrl_rss.append(pm['controller_server_rss'])
        if pm['planner_server_cpu'] > 0.0 or pm['planner_server_rss'] > 0.0:
            self.hist_plan_cpu.append(pm['planner_server_cpu'])
            self.hist_plan_rss.append(pm['planner_server_rss'])
        if pm['nav2_total_cpu'] > 0.0 or pm['nav2_total_rss'] > 0.0:
            self.hist_nav2_cpu.append(pm['nav2_total_cpu'])
            self.hist_nav2_rss.append(pm['nav2_total_rss'])

        row = {
            'elapsed_s': round(elapsed, 2),
            'timestamp': datetime.now().strftime('%H:%M:%S.%f')[:-3],
            'sim_time_s': round(sim_time_s, 2),
            'mode_label': self.mode_label,
            'nav_status': self.nav_status,
            'fsm_status': self.fsm_status,
            'map_x': round(map_x, 4) if map_x is not None else '',
            'map_y': round(map_y, 4) if map_y is not None else '',
            'map_yaw': round(map_yaw, 4) if map_yaw is not None else '',
            'total_dist_m': round(self.total_distance_m, 3),
            'odom_x': round(self.odom_x, 4),
            'odom_y': round(self.odom_y, 4),
            'odom_yaw': round(self.odom_yaw, 4),
            'v_lin': round(self.v_lin, 3),
            'v_ang': round(self.v_ang, 3),
            'map_odom_dx': round(mo_x, 4) if mo_x is not None else '',
            'map_odom_dy': round(mo_y, 4) if mo_y is not None else '',
            'map_odom_dyaw': round(mo_yaw, 4) if mo_yaw is not None else '',
            'graph_nodes': self.graph_nodes,
            'graph_edges': self.graph_edges,
            'map_width': self.map_width,
            'map_height': self.map_height,
            'map_free_cells': self.map_free_cells,
            'map_occ_cells': self.map_occ_cells,
            'map_updates': self.map_updates_count,
            'slam_cpu_pct': pm['slam_toolbox_cpu'],
            'slam_rss_mb': pm['slam_toolbox_rss'],
            'controller_cpu_pct': pm['controller_server_cpu'],
            'controller_rss_mb': pm['controller_server_rss'],
            'planner_cpu_pct': pm['planner_server_cpu'],
            'planner_rss_mb': pm['planner_server_rss'],
            'bt_nav_cpu_pct': pm['bt_navigator_cpu'],
            'bt_nav_rss_mb': pm['bt_navigator_rss'],
            'nav2_total_cpu_pct': pm['nav2_total_cpu'],
            'nav2_total_rss_mb': pm['nav2_total_rss'],
            'sys_cpu_pct': round(sys_cpu, 2),
            'sys_ram_used_mb': round(sys_ram_mb, 1),
        }

        self.csv_writer.writerow(row)
        self.rows_written += 1

        # Сбрасываем буфер на диск каждые 10 строк и обновляем паспорт каждые 30 строк
        if self.rows_written % 10 == 0:
            self.csv_file.flush()
            self.get_logger().info(
                f"[{self.mode_label}] t={elapsed:.0f}s | dist={self.total_distance_m:.1f}m | "
                f"graph={self.graph_nodes}v/{self.graph_edges}e | "
                f"SLAM CPU={pm['slam_toolbox_cpu']:.1f}% RSS={pm['slam_toolbox_rss']:.1f}MB | "
                f"Nav2 CPU={pm['nav2_total_cpu']:.1f}%"
            )
        if self.rows_written % 30 == 0:
            self._update_passport_summary()

    def _update_passport_summary(self):
        elapsed = time.time() - self.start_wall_time
        self.passport_data["end_time_iso"] = datetime.now().isoformat()
        self.passport_data["summary"] = {
            "duration_s": round(elapsed, 2),
            "samples_recorded": self.rows_written,
            "total_distance_traveled_m": round(self.total_distance_m, 3),
            "pose_graph": {
                "nodes_start": self.graph_nodes_start,
                "nodes_end": self.graph_nodes,
                "nodes_added": (self.graph_nodes - self.graph_nodes_start) if self.graph_nodes_start is not None else 0,
                "edges_start": self.graph_edges_start,
                "edges_end": self.graph_edges,
                "edges_added": (self.graph_edges - self.graph_edges_start) if self.graph_edges_start is not None else 0,
            },
            "map_grid": {
                "width": self.map_width,
                "height": self.map_height,
                "resolution_m": self.map_res,
                "free_cells_end": self.map_free_cells,
                "free_area_m2_end": round(self.map_free_cells * (self.map_res ** 2), 3),
                "map_updates_received": self.map_updates_count,
            },
            "performance": {
                "slam_toolbox_cpu_pct": calc_stats(self.hist_slam_cpu),
                "slam_toolbox_rss_mb": calc_stats(self.hist_slam_rss),
                "controller_server_cpu_pct": calc_stats(self.hist_ctrl_cpu),
                "controller_server_rss_mb": calc_stats(self.hist_ctrl_rss),
                "planner_server_cpu_pct": calc_stats(self.hist_plan_cpu),
                "planner_server_rss_mb": calc_stats(self.hist_plan_rss),
                "nav2_total_cpu_pct": calc_stats(self.hist_nav2_cpu),
                "nav2_total_rss_mb": calc_stats(self.hist_nav2_rss),
            }
        }
        self._save_passport()

    def close_logger(self):
        self._update_passport_summary()
        try:
            self.csv_file.flush()
            self.csv_file.close()
        except Exception:
            pass
        self.get_logger().info("==========================================================")
        self.get_logger().info(f"[Block 2B Logger] FINISHED ({self.rows_written} rows, {self.total_distance_m:.1f} m)")
        self.get_logger().info(f"  Saved CSV     : {self.csv_path}")
        self.get_logger().info(f"  Saved Passport: {self.passport_path}")
        self.get_logger().info("==========================================================")


def main(args=None):
    rclpy.init(args=args)
    node = Block2BLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close_logger()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
