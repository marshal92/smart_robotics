#!/usr/bin/env python3
"""
Recovery Relocalizer — автоматическое восстановление локализации.

По команде 'recover_localization' из /smart_command:
1. Останавливает робота (cancel)
2. Паузит SLAM (toggle pause)
3. Загружает PGM-карту с диска (2D-картинка стен)
4. Глобальный Coarse-to-Fine скан-матчинг: ищет (x, y, yaw) робота
5. Горячо перезагружает чистый posegraph в SLAM Toolbox с найденной позой
   через сервис /slam_toolbox/deserialize_map (НЕ через tmux/launch!)
6. Снимает паузу SLAM

Нода живёт в smart_control, запускается из control_core.launch.py,
ждёт команду и ничего не делает пока её не позовут.

TODO: в будущем читать имя активной карты из SmartTelemetry
      вместо хардкода.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

import numpy as np
import math
import threading
import time
import os
import yaml

from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import PoseWithCovarianceStamped, Pose2D
from slam_toolbox.srv import DeserializePoseGraph, Pause
from smart_interfaces.msg import SmartCommand


class RecoveryRelocalizer(Node):
    def __init__(self):
        super().__init__('recovery_relocalizer')

        # === Параметры ===
        self.declare_parameter('maps_dir',
                               '/home/oleksandr/ros2_ws/src/smart_robotics/smart_nav/maps')
        self.declare_parameter('default_map', '213_map')
        self.declare_parameter('coarse_step_m', 0.25)
        self.declare_parameter('coarse_angle_step_deg', 10.0)
        self.declare_parameter('fine_step_m', 0.05)
        self.declare_parameter('fine_angle_step_deg', 2.0)
        self.declare_parameter('scan_decimation', 3)
        self.declare_parameter('min_match_percent', 25.0)

        self.maps_dir = self.get_parameter('maps_dir').value
        self.default_map = self.get_parameter('default_map').value
        self.coarse_step = self.get_parameter('coarse_step_m').value
        self.coarse_angle_step = math.radians(
            self.get_parameter('coarse_angle_step_deg').value)
        self.fine_step = self.get_parameter('fine_step_m').value
        self.fine_angle_step = math.radians(
            self.get_parameter('fine_angle_step_deg').value)
        self.scan_decimation = self.get_parameter('scan_decimation').value
        self.min_match_pct = self.get_parameter('min_match_percent').value

        # === Состояние ===
        self.latest_scan = None
        self.is_recovering = False
        self._lock = threading.Lock()

        # === Подписки ===
        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE
        )
        self.create_subscription(
            SmartCommand, '/smart_command', self._command_cb, qos)
        self.create_subscription(
            LaserScan, '/scan', self._scan_cb, 10)

        # === Публикации ===
        self.cmd_pub = self.create_publisher(SmartCommand, '/smart_command', 10)
        self.initialpose_pub = self.create_publisher(
            PoseWithCovarianceStamped, '/initialpose', 10)

        # === Сервис-клиенты (к уже работающему SLAM Toolbox) ===
        self.pause_cli = self.create_client(
            Pause, '/slam_toolbox/pause_new_measurements')
        self.deserialize_cli = self.create_client(
            DeserializePoseGraph, '/slam_toolbox/deserialize_map')

        self.get_logger().info(
            f"Recovery Relocalizer ready. Default map: {self.default_map}")

    # ================================================================
    #  Колбэки
    # ================================================================

    def _scan_cb(self, msg):
        self.latest_scan = msg

    def _command_cb(self, msg):
        if msg.target_system != 'nav' or msg.command != 'recover_localization':
            return

        with self._lock:
            if self.is_recovering:
                self.get_logger().warn("Recovery already in progress!")
                return
            self.is_recovering = True

        # Читаем имя карты из payload (если есть), иначе — default
        map_name = self.default_map
        if msg.payload_json:
            try:
                import json
                payload = json.loads(msg.payload_json)
                map_name = payload.get('map', self.default_map)
            except Exception:
                pass

        self.get_logger().warn(
            "╔══════════════════════════════════════════╗")
        self.get_logger().warn(
            "║   RECOVERY RELOCALIZATION TRIGGERED      ║")
        self.get_logger().warn(
            f"║   Map: {map_name:<33s}║")
        self.get_logger().warn(
            "╚══════════════════════════════════════════╝")

        threading.Thread(
            target=self._run_recovery, args=(map_name,), daemon=True
        ).start()

    # ================================================================
    #  Основной пайплайн восстановления
    # ================================================================

    def _run_recovery(self, map_name):
        try:
            # --- 1. Остановка робота ---
            self.get_logger().info("[1/6] Stopping robot...")
            self.cmd_pub.publish(
                SmartCommand(target_system='nav', command='cancel'))
            time.sleep(0.5)

            # --- 2. Пауза SLAM (toggle) ---
            self.get_logger().info("[2/6] Pausing SLAM...")
            self._toggle_slam_pause()
            time.sleep(0.3)

            # --- 3. Загрузка PGM-карты с диска ---
            self.get_logger().info("[3/6] Loading reference map from disk...")
            map_data = self._load_pgm_map(map_name)
            if map_data is None:
                self.get_logger().error(
                    "Failed to load map! Aborting recovery.")
                self._toggle_slam_pause()
                return

            wall_mask, free_mask, res, ox, oy, w, h = map_data

            # --- 4. Текущий скан лидара ---
            self.get_logger().info("[4/6] Acquiring laser scan...")
            if self.latest_scan is None:
                self.get_logger().error("No scan data available! Aborting.")
                self._toggle_slam_pause()
                return

            lx, ly = self._scan_to_points(self.latest_scan)
            if len(lx) < 10:
                self.get_logger().error(
                    f"Too few valid scan points ({len(lx)}). Aborting.")
                self._toggle_slam_pause()
                return

            self.get_logger().info(
                f"  Scan: {len(lx)} points (after decimation)")

            # --- 5. Глобальный скан-матчинг ---
            self.get_logger().info(
                f"[5/6] Global scan matching ({len(lx)} pts vs "
                f"{w}x{h} map)...")

            t0 = time.time()
            bx, by, byaw, score, n_pts = self._global_scan_match(
                lx, ly, wall_mask, free_mask, res, ox, oy, w, h)
            dt = time.time() - t0

            if score < 0:
                self.get_logger().error(
                    "No valid position found on map! Aborting.")
                self._toggle_slam_pause()
                return

            pct = (score / n_pts * 100.0) if n_pts > 0 else 0.0
            self.get_logger().info(
                f"  ► Position found in {dt:.2f}s: "
                f"x={bx:.3f} y={by:.3f} yaw={math.degrees(byaw):.1f}°  "
                f"score={score:.0f}/{n_pts} ({pct:.1f}%)")

            if pct < self.min_match_pct:
                self.get_logger().warn(
                    f"  Low confidence ({pct:.1f}% < {self.min_match_pct}%). "
                    f"Proceeding anyway — verify in RViz!")

            # --- 6. Горячая перезагрузка posegraph ---
            self.get_logger().info(
                "[6/6] Hot-reloading posegraph with found position...")
            self._reload_posegraph(map_name, bx, by, byaw)
            time.sleep(1.5)

            # Страховка: дублируем через /initialpose
            self._publish_initialpose(bx, by, byaw)
            time.sleep(0.5)

            # Снимаем паузу (toggle обратно)
            self._toggle_slam_pause()

            self.get_logger().info(
                "╔══════════════════════════════════════════╗")
            self.get_logger().info(
                f"║   RECOVERY COMPLETE                      ║")
            self.get_logger().info(
                f"║   x={bx:+7.3f}  y={by:+7.3f}  "
                f"yaw={math.degrees(byaw):+6.1f}°     ║")
            self.get_logger().info(
                "╚══════════════════════════════════════════╝")

        except Exception as e:
            self.get_logger().error(f"Recovery failed with exception: {e}")
            import traceback
            self.get_logger().error(traceback.format_exc())
            # Пытаемся снять паузу даже при ошибке
            try:
                self._toggle_slam_pause()
            except Exception:
                pass
        finally:
            with self._lock:
                self.is_recovering = False

    # ================================================================
    #  Загрузка карты с диска (PGM + YAML)
    # ================================================================

    def _load_pgm_map(self, map_name):
        """
        Загружает PGM + YAML файлы карты.
        Возвращает (wall_mask, free_mask, resolution, origin_x, origin_y, w, h)
        или None при ошибке.
        
        wall_mask: float32 ndarray, 1.0 = стена (для скоринга)
        free_mask: bool ndarray, True = свободно (для перебора позиций)
        
        Массивы в системе координат OccupancyGrid:
          row 0 = низ карты (origin_y),
          col 0 = левый край (origin_x).
        """
        yaml_path = os.path.join(self.maps_dir, f"{map_name}.yaml")
        if not os.path.exists(yaml_path):
            self.get_logger().error(f"YAML not found: {yaml_path}")
            return None

        with open(yaml_path, 'r') as f:
            meta = yaml.safe_load(f)

        resolution = float(meta['resolution'])
        origin = meta['origin']
        origin_x, origin_y = float(origin[0]), float(origin[1])
        occ_thresh = float(meta.get('occupied_thresh', 0.65))
        free_thresh = float(meta.get('free_thresh', 0.196))
        negate = bool(int(meta.get('negate', 0)))

        # Ищем PGM: сначала по YAML, потом фоллбэк на {map_name}.pgm
        pgm_name = meta.get('image', f'{map_name}.pgm')
        pgm_path = os.path.join(self.maps_dir, pgm_name)
        if not os.path.exists(pgm_path):
            pgm_path = os.path.join(self.maps_dir, f'{map_name}.pgm')
        if not os.path.exists(pgm_path):
            self.get_logger().error(f"PGM not found: {pgm_path}")
            return None

        # Загрузка изображения
        pixels = self._load_image(pgm_path)
        if pixels is None:
            return None

        # Переворачиваем по вертикали: PGM row=0 это верх картинки,
        # а нам нужен row=0 = низ (как в OccupancyGrid)
        pixels = np.flipud(pixels).astype(np.float32)

        # Вероятность занятости
        if negate:
            prob = pixels / 255.0
        else:
            prob = (255.0 - pixels) / 255.0

        wall_binary = (prob > occ_thresh).astype(np.float32)
        free_mask = (prob < free_thresh)

        # Gaussian Smear: "размазываем" стены на ±3 пикселя (~15 см).
        # Без этого score падает в ноль при сдвиге на 1 пиксель (5 см),
        # и грубый поиск с шагом 25 см не попадает в правильную позу.
        # Это стандартный приём Correlative Scan Matcher.
        try:
            from scipy.ndimage import gaussian_filter
            wall_mask = gaussian_filter(wall_binary, sigma=3.0)
            # Нормализуем чтобы максимум был 1.0
            wmax = wall_mask.max()
            if wmax > 0:
                wall_mask = wall_mask / wmax
        except ImportError:
            self.get_logger().warn(
                "scipy not available — using raw wall mask (less robust)")
            wall_mask = wall_binary

        h, w = pixels.shape
        n_walls = int(np.sum(wall_binary))
        n_free = int(np.sum(free_mask))

        self.get_logger().info(
            f"  Map: {w}x{h} px, res={resolution}m, "
            f"origin=({origin_x:.2f}, {origin_y:.2f}), "
            f"walls={n_walls}, free={n_free}")

        return wall_mask, free_mask, resolution, origin_x, origin_y, w, h

    def _load_image(self, path):
        """Загружает PGM через cv2 или PIL (что найдётся)."""
        try:
            import cv2
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                return img
        except ImportError:
            pass

        try:
            from PIL import Image
            return np.array(Image.open(path))
        except ImportError:
            pass

        self.get_logger().error(
            "Neither cv2 nor PIL available! Install: "
            "pip install opencv-python-headless  OR  pip install Pillow")
        return None

    # ================================================================
    #  Обработка лидарного скана
    # ================================================================

    def _scan_to_points(self, scan):
        """LaserScan → массивы (lx, ly) точек в base_link."""
        ranges = np.array(scan.ranges, dtype=np.float32)
        angles = (scan.angle_min +
                  np.arange(len(ranges)) * scan.angle_increment)

        valid = ((ranges > scan.range_min) &
                 (ranges < scan.range_max) &
                 np.isfinite(ranges))
        ranges = ranges[valid]
        angles = angles[valid]

        # Децимация для ускорения
        if self.scan_decimation > 1:
            ranges = ranges[::self.scan_decimation]
            angles = angles[::self.scan_decimation]

        lx = ranges * np.cos(angles)
        ly = ranges * np.sin(angles)
        return lx, ly

    # ================================================================
    #  Глобальный скан-матчинг (Coarse-to-Fine)
    # ================================================================

    def _global_scan_match(self, lx, ly, wall_mask, free_mask,
                           res, ox, oy, w, h):
        """
        Перебирает все возможные (x, y, yaw) на карте.
        Для каждой гипотезы проецирует точки лидара и считает,
        сколько попало в стены.

        Возвращает (best_x, best_y, best_yaw, best_score, n_points).
        """
        n_pts = len(lx)
        step_cells = max(1, int(self.coarse_step / res))
        yaw_steps = np.arange(0, 2 * np.pi, self.coarse_angle_step)

        best_score = -1.0
        best_pose = (0.0, 0.0, 0.0)
        candidates = []  # (score, x, y, yaw) для fine pass

        # --- Грубый проход ---
        n_checked = 0
        for r in range(0, h, step_cells):
            for c in range(0, w, step_cells):
                if not free_mask[r, c]:
                    continue

                wx = ox + (c + 0.5) * res
                wy = oy + (r + 0.5) * res

                for yaw in yaw_steps:
                    s = self._score_pose(
                        wx, wy, yaw, lx, ly,
                        wall_mask, res, ox, oy, w, h)
                    n_checked += 1

                    if s > best_score:
                        best_score = s
                        best_pose = (wx, wy, yaw)

                    # Кандидаты для уточнения
                    if s > n_pts * 0.2:
                        candidates.append((s, wx, wy, yaw))

        self.get_logger().info(
            f"  Coarse: checked {n_checked} hypotheses, "
            f"best={best_score:.0f}/{n_pts}")

        if best_score < 0:
            return 0.0, 0.0, 0.0, -1.0, n_pts

        # --- Дедупликация кандидатов (убираем близкие) ---
        candidates.sort(key=lambda c: c[0], reverse=True)
        unique = []
        for s, cx, cy, cyaw in candidates:
            dup = False
            for _, ux, uy, _ in unique:
                if (abs(cx - ux) < self.coarse_step and
                        abs(cy - uy) < self.coarse_step):
                    dup = True
                    break
            if not dup:
                unique.append((s, cx, cy, cyaw))
            if len(unique) >= 5:
                break

        self.get_logger().info(
            f"  Fine: refining {len(unique)} candidates...")

        # --- Точный проход ---
        radius = self.coarse_step
        fine_yaws = np.arange(
            -self.coarse_angle_step, self.coarse_angle_step,
            self.fine_angle_step)

        for _, cx, cy, cyaw in unique:
            for dx in np.arange(-radius, radius + 1e-6, self.fine_step):
                for dy in np.arange(-radius, radius + 1e-6, self.fine_step):
                    for dyaw in fine_yaws:
                        s = self._score_pose(
                            cx + dx, cy + dy, cyaw + dyaw,
                            lx, ly, wall_mask, res, ox, oy, w, h)
                        if s > best_score:
                            best_score = s
                            best_pose = (cx + dx, cy + dy, cyaw + dyaw)

        return (*best_pose, best_score, n_pts)

    def _score_pose(self, wx, wy, yaw, lx, ly,
                    wall_mask, res, ox, oy, w, h):
        """Оценка гипотезы: % точек скана, попавших в стены карты."""
        cos_y = math.cos(yaw)
        sin_y = math.sin(yaw)

        # Поворот + сдвиг облака точек в мировые координаты
        gx = wx + (lx * cos_y - ly * sin_y)
        gy = wy + (lx * sin_y + ly * cos_y)

        # Мировые → индексы карты
        mx = ((gx - ox) / res).astype(np.int32)
        my = ((gy - oy) / res).astype(np.int32)

        # Границы
        valid = (mx >= 0) & (mx < w) & (my >= 0) & (my < h)
        n_valid = np.count_nonzero(valid)
        if n_valid == 0:
            return -1.0

        return float(np.sum(wall_mask[my[valid], mx[valid]]))

    # ================================================================
    #  Управление SLAM Toolbox
    # ================================================================

    def _toggle_slam_pause(self):
        """Toggle пауза SLAM (как в mission_manager)."""
        if not self.pause_cli.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn(
                "SLAM pause service not available! Skipping.")
            return
        self.pause_cli.call_async(Pause.Request())
        self.get_logger().info("  SLAM pause toggled")

    def _reload_posegraph(self, map_name, x, y, yaw):
        """
        Горячая перезагрузка чистого posegraph в уже работающий
        SLAM Toolbox с указанием найденной позы.
        НЕ перезапускает ноду, НЕ трогает tmux.
        """
        if not self.deserialize_cli.wait_for_service(timeout_sec=3.0):
            self.get_logger().error(
                "DeserializePoseGraph service not available!")
            return

        # Путь без расширения — SLAM Toolbox сам добавит .posegraph/.data
        posegraph_path = os.path.join(self.maps_dir, map_name)

        req = DeserializePoseGraph.Request()
        req.filename = posegraph_path
        req.match_type = 3  # LOCALIZE_AT_POSE
        req.initial_pose = Pose2D(x=x, y=y, theta=yaw)

        self.get_logger().info(
            f"  Deserializing: {posegraph_path}")
        self.get_logger().info(
            f"  Initial pose: x={x:.3f}, y={y:.3f}, "
            f"theta={math.degrees(yaw):.1f}°")

        self.deserialize_cli.call_async(req)

    def _publish_initialpose(self, x, y, yaw):
        """Дублирует позу через /initialpose для страховки."""
        msg = PoseWithCovarianceStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        msg.pose.pose.position.x = float(x)
        msg.pose.pose.position.y = float(y)
        msg.pose.pose.orientation.z = math.sin(float(yaw) / 2.0)
        msg.pose.pose.orientation.w = math.cos(float(yaw) / 2.0)
        # Жёсткая ковариация (высокая уверенность)
        msg.pose.covariance[0] = 0.05   # X
        msg.pose.covariance[7] = 0.05   # Y
        msg.pose.covariance[35] = 0.02  # Yaw
        self.initialpose_pub.publish(msg)
        self.get_logger().info("  Published /initialpose (backup)")


def main(args=None):
    rclpy.init(args=args)
    node = RecoveryRelocalizer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
