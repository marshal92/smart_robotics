#!/usr/bin/env python3
"""
Recovery Relocalizer — automatic localization recovery node.

Triggered by 'recover_localization' on /smart_command:
1. Stops the robot (cancel)
2. Pauses SLAM (toggle pause)
3. Loads PGM occupancy map from disk (2D wall image)
4. Runs global Coarse-to-Fine scan matching to estimate robot (x, y, yaw)
5. Hot-reloads clean posegraph into SLAM Toolbox with the recovered pose
   via /slam_toolbox/deserialize_map service (WITHOUT restarting tmux/launch)
6. Unpauses SLAM

Runs inside smart_control (launched by control_core.launch.py),
staying idle until triggered.

TODO: Read the active map name dynamically from SmartTelemetry instead of hardcoding.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, qos_profile_sensor_data

import json
import numpy as np
import math
import threading
import time
import os
import yaml

try:
    from ament_index_python.packages import get_package_share_directory
except ImportError:
    get_package_share_directory = None

from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import PoseWithCovarianceStamped, Pose2D
from slam_toolbox.srv import DeserializePoseGraph, Pause
from smart_interfaces.msg import SmartCommand


class RecoveryRelocalizer(Node):
    def __init__(self):
        super().__init__('recovery_relocalizer')

        # === Parameters ===
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

        # === State ===
        self.latest_scan = None
        self.is_recovering = False
        self._lock = threading.Lock()

        # === Subscriptions ===
        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE
        )
        self.create_subscription(
            SmartCommand, '/smart_command', self._command_cb, qos)
        self.create_subscription(
            LaserScan, '/scan', self._scan_cb, qos_profile_sensor_data)

        # === Publications ===
        self.cmd_pub = self.create_publisher(SmartCommand, '/smart_command', 10)
        self.initialpose_pub = self.create_publisher(
            PoseWithCovarianceStamped, '/initialpose', 10)

        # === Service Clients (targeting active SLAM Toolbox) ===
        self.pause_cli = self.create_client(
            Pause, '/slam_toolbox/pause_new_measurements')
        self.deserialize_cli = self.create_client(
            DeserializePoseGraph, '/slam_toolbox/deserialize_map')

        self.get_logger().info(
            f"Recovery Relocalizer ready. Default map: {self.default_map}")

    # ================================================================
    #  Callbacks
    # ================================================================

    def _scan_cb(self, msg):
        self.latest_scan = msg

    def _command_cb(self, msg):
        if msg.target_system != 'nav' or msg.command.strip().lower() != 'recover_localization':
            return

        with self._lock:
            if self.is_recovering:
                self.get_logger().warn("Recovery already in progress!")
                return
            self.is_recovering = True

        # Read map name from payload if provided, otherwise fall back to default
        raw_map_name = self.default_map
        if msg.payload_json:
            try:
                payload = json.loads(msg.payload_json)
                if isinstance(payload, dict):
                    raw_map_name = payload.get('map') or payload.get('map_name') or self.default_map
            except Exception as exc:
                self.get_logger().warn(f"Invalid payload_json in recover_localization ({exc}); using default map.")

        map_name = self._normalize_map_name(str(raw_map_name))

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

    @staticmethod
    def _normalize_map_name(raw_name: str) -> str:
        name = raw_name.strip()
        for ext in ('.posegraph', '.yaml', '.pgm', '.data'):
            if name.endswith(ext):
                name = name[:-len(ext)]
                break
        aliases = {
            '213': '213_map',
            'start_213': '213_map',
            'start_kitchen': 'kitchen_map',
            'start_shelter_zero': 'shelter_012.7',
            'start_shelter': 'shelter_map',
        }
        return aliases.get(name.lower(), name)

    def _find_map_base(self, map_name: str):
        candidate_dirs = []
        for d in (
            os.path.expanduser(str(self.maps_dir)),
            os.path.expanduser('~/.local/share/smart_robotics/nav_maps'),
        ):
            if d and d not in candidate_dirs:
                candidate_dirs.append(d)

        if get_package_share_directory is not None:
            try:
                share_maps = os.path.join(get_package_share_directory('smart_nav'), 'maps')
                if share_maps not in candidate_dirs:
                    candidate_dirs.append(share_maps)
            except Exception:
                pass

        for directory in candidate_dirs:
            yaml_path = os.path.join(directory, f"{map_name}.yaml")
            if os.path.exists(yaml_path):
                return os.path.join(directory, map_name)

        self.get_logger().error(
            f"Map '{map_name}.yaml' not found in searched dirs: {candidate_dirs}")
        return None

    # ================================================================
    #  Main Recovery Pipeline
    # ================================================================

    def _run_recovery(self, map_name):
        slam_paused = False
        try:
            # --- 0. Verify map files & SLAM Toolbox availability before work ---
            map_base = self._find_map_base(map_name)
            if map_base is None:
                return
            posegraph_file = f"{map_base}.posegraph"
            if not os.path.exists(posegraph_file):
                self.get_logger().error(
                    f"Posegraph not found: {posegraph_file}. Cannot run SLAM recovery.")
                return

            if not self.deserialize_cli.wait_for_service(timeout_sec=1.5):
                self.get_logger().error(
                    "Service /slam_toolbox/deserialize_map is not available! Start a map mission first.")
                return

            if self.latest_scan is None:
                self.get_logger().error("No scan data available yet on /scan! Aborting.")
                return

            # --- 1. Stop robot ---
            self.get_logger().info("[1/6] Stopping robot...")
            self.cmd_pub.publish(
                SmartCommand(target_system='nav', command='cancel'))
            time.sleep(0.5)

            # --- 2. Pause SLAM (toggle) ---
            self.get_logger().info("[2/6] Pausing SLAM...")
            slam_paused = self._toggle_slam_pause()
            time.sleep(0.2)

            # --- 3. Load PGM map from disk ---
            self.get_logger().info("[3/6] Loading reference map from disk...")
            map_data = self._load_pgm_map(map_base)
            if map_data is None:
                self.get_logger().error(
                    "Failed to load map! Aborting recovery.")
                return

            wall_mask, free_mask, res, ox, oy, w, h = map_data

            # --- 4. Acquire current LiDAR scan ---
            self.get_logger().info("[4/6] Acquiring laser scan...")
            if self.latest_scan is None:
                self.get_logger().error("No scan data available! Aborting.")
                return

            lx, ly = self._scan_to_points(self.latest_scan)
            if len(lx) < 10:
                self.get_logger().error(
                    f"Too few valid scan points ({len(lx)}). Aborting.")
                return

            self.get_logger().info(
                f"  Scan: {len(lx)} points (after decimation)")

            # --- 5. Global scan matching ---
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

            # --- 6. Hot-reload posegraph ---
            self.get_logger().info(
                "[6/6] Hot-reloading posegraph with found position...")
            reloaded = self._reload_posegraph(map_base, bx, by, byaw)
            if not reloaded:
                self.get_logger().error("Posegraph deserialization failed or timed out!")

            # Safeguard: also publish via /initialpose
            self._publish_initialpose(bx, by, byaw)
            time.sleep(0.3)

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
        finally:
            if slam_paused:
                try:
                    self._toggle_slam_pause()
                except Exception:
                    pass
            with self._lock:
                self.is_recovering = False

    # ================================================================
    #  Map Loading from Disk (PGM + YAML)
    # ================================================================

    def _load_pgm_map(self, map_base):
        """
        Load PGM + YAML map files from a base path (without extension).
        Returns (wall_mask, free_mask, resolution, origin_x, origin_y, w, h)
        or None on failure.
        """
        map_dir = os.path.dirname(map_base)
        map_name = os.path.basename(map_base)
        yaml_path = f"{map_base}.yaml"
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

        # Locate PGM: prefer YAML image entry, then fall back to {map_name}.pgm
        pgm_name = meta.get('image', f'{map_name}.pgm')
        pgm_path = pgm_name if os.path.isabs(pgm_name) else os.path.join(map_dir, pgm_name)
        if not os.path.exists(pgm_path):
            pgm_path = f"{map_base}.pgm"
        if not os.path.exists(pgm_path):
            self.get_logger().error(f"PGM not found: {pgm_path}")
            return None

        # Load image
        pixels = self._load_image(pgm_path)
        if pixels is None:
            return None

        # Flip vertically: PGM row=0 is top of image,
        # whereas OccupancyGrid uses row=0 as bottom
        pixels = np.flipud(pixels).astype(np.float32)

        # Occupancy probability
        if negate:
            prob = pixels / 255.0
        else:
            prob = (255.0 - pixels) / 255.0

        wall_binary = (prob > occ_thresh).astype(np.float32)
        free_mask = (prob < free_thresh)

        # Gaussian Smear: blur walls across +-3 pixels (~15 cm).
        # Without this, score drops to zero on a 1-pixel (5 cm) offset,
        # causing the 25 cm coarse grid search to miss the true pose.
        # Standard Correlative Scan Matcher technique.
        try:
            from scipy.ndimage import gaussian_filter
            wall_mask = gaussian_filter(wall_binary, sigma=3.0)
            # Normalize peak to 1.0
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
        """Load PGM via cv2 or PIL (whichever is available)."""
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
    #  LiDAR Scan Processing
    # ================================================================

    def _scan_to_points(self, scan):
        """LaserScan -> arrays (lx, ly) of points in base_link."""
        ranges = np.array(scan.ranges, dtype=np.float32)
        angles = (scan.angle_min +
                  np.arange(len(ranges)) * scan.angle_increment)

        valid = ((ranges > scan.range_min) &
                 (ranges < scan.range_max) &
                 np.isfinite(ranges))
        ranges = ranges[valid]
        angles = angles[valid]

        # Decimate scan rays for speed
        if self.scan_decimation > 1:
            ranges = ranges[::self.scan_decimation]
            angles = angles[::self.scan_decimation]

        lx = ranges * np.cos(angles)
        ly = ranges * np.sin(angles)
        return lx, ly

    # ================================================================
    #  Global Scan Matching (Coarse-to-Fine)
    # ================================================================

    def _global_scan_match(self, lx, ly, wall_mask, free_mask,
                           res, ox, oy, w, h):
        """
        Exhaustively evaluates candidate (x, y, yaw) poses across the map.
        Projects LiDAR scan points for each hypothesis and sums wall overlap score.

        Returns (best_x, best_y, best_yaw, best_score, n_points).
        """
        n_pts = len(lx)
        step_cells = max(1, int(self.coarse_step / res))
        yaw_steps = np.arange(0, 2 * np.pi, self.coarse_angle_step)

        # Precompute rotated scan offsets in grid cell units once per yaw angle
        coarse_rotations = []
        for yaw in yaw_steps:
            cos_y = math.cos(yaw)
            sin_y = math.sin(yaw)
            rx_cells = (lx * cos_y - ly * sin_y) / res
            ry_cells = (lx * sin_y + ly * cos_y) / res
            coarse_rotations.append((float(yaw), rx_cells, ry_cells))

        best_score = -1.0
        best_pose = (0.0, 0.0, 0.0)
        candidates = []  # (score, x, y, yaw) for fine pass

        # --- Coarse pass ---
        n_checked = 0
        for r in range(0, h, step_cells):
            for c in range(0, w, step_cells):
                if not free_mask[r, c]:
                    continue

                cx_base = c + 0.5
                cy_base = r + 0.5
                wx = ox + cx_base * res
                wy = oy + cy_base * res

                for yaw, rx_cells, ry_cells in coarse_rotations:
                    mx = (cx_base + rx_cells).astype(np.int32)
                    my = (cy_base + ry_cells).astype(np.int32)
                    valid = (mx >= 0) & (mx < w) & (my >= 0) & (my < h)
                    if not np.any(valid):
                        s = -1.0
                    else:
                        s = float(np.sum(wall_mask[my[valid], mx[valid]]))
                    n_checked += 1

                    if s > best_score:
                        best_score = s
                        best_pose = (wx, wy, yaw)

                    if s > n_pts * 0.2:
                        candidates.append((s, wx, wy, yaw))

        self.get_logger().info(
            f"  Coarse: checked {n_checked} hypotheses, "
            f"best={best_score:.0f}/{n_pts}")

        if best_score < 0:
            return 0.0, 0.0, 0.0, -1.0, n_pts

        # --- Candidate deduplication (drop nearby duplicates) ---
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

        # --- Fine pass ---
        radius = self.coarse_step
        fine_yaws = np.arange(
            -self.coarse_angle_step, self.coarse_angle_step,
            self.fine_angle_step)

        for _, cx, cy, cyaw in unique:
            for dyaw in fine_yaws:
                yaw_cand = cyaw + float(dyaw)
                cos_y = math.cos(yaw_cand)
                sin_y = math.sin(yaw_cand)
                rx_world = lx * cos_y - ly * sin_y
                ry_world = lx * sin_y + ly * cos_y
                for dx in np.arange(-radius, radius + 1e-6, self.fine_step):
                    for dy in np.arange(-radius, radius + 1e-6, self.fine_step):
                        s = self._score_rotated(
                            cx + float(dx), cy + float(dy),
                            rx_world, ry_world, wall_mask, res, ox, oy, w, h)
                        if s > best_score:
                            best_score = s
                            best_pose = (cx + float(dx), cy + float(dy), yaw_cand)

        return (*best_pose, best_score, n_pts)

    @staticmethod
    def _score_rotated(wx, wy, rx, ry, wall_mask, res, ox, oy, w, h):
        """Hypothesis score from pre-rotated scan offsets."""
        mx = ((wx + rx - ox) / res).astype(np.int32)
        my = ((wy + ry - oy) / res).astype(np.int32)
        valid = (mx >= 0) & (mx < w) & (my >= 0) & (my < h)
        if not np.any(valid):
            return -1.0
        return float(np.sum(wall_mask[my[valid], mx[valid]]))

    # ================================================================
    #  SLAM Toolbox Control
    # ================================================================

    def _call_service_sync(self, client, req, wait_srv_s=2.0, call_timeout_s=5.0):
        if not client.wait_for_service(timeout_sec=wait_srv_s):
            return False, None
        done = threading.Event()
        fut = client.call_async(req)
        fut.add_done_callback(lambda _: done.set())
        if not done.wait(timeout=call_timeout_s):
            return False, None
        try:
            return True, fut.result()
        except Exception:
            return False, None

    def _toggle_slam_pause(self) -> bool:
        """Toggle SLAM pause (same service as mission_manager)."""
        ok, _ = self._call_service_sync(
            self.pause_cli, Pause.Request(), wait_srv_s=2.0, call_timeout_s=3.0)
        if not ok:
            self.get_logger().warn(
                "SLAM pause service not available! Skipping.")
            return False
        self.get_logger().info("  SLAM pause toggled")
        return True

    def _reload_posegraph(self, map_base, x, y, yaw) -> bool:
        """
        Hot-reload a clean posegraph into the running SLAM Toolbox instance
        at the recovered pose.
        Does NOT restart the node or touch tmux.
        """
        req = DeserializePoseGraph.Request()
        req.filename = map_base
        req.match_type = 3  # LOCALIZE_AT_POSE
        req.initial_pose = Pose2D(x=x, y=y, theta=yaw)

        self.get_logger().info(f"  Deserializing: {map_base}")
        self.get_logger().info(
            f"  Initial pose: x={x:.3f}, y={y:.3f}, "
            f"theta={math.degrees(yaw):.1f}°")

        ok, _ = self._call_service_sync(
            self.deserialize_cli, req, wait_srv_s=3.0, call_timeout_s=8.0)
        return ok

    def _publish_initialpose(self, x, y, yaw):
        """Also publish pose to /initialpose as a fallback safeguard."""
        msg = PoseWithCovarianceStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        msg.pose.pose.position.x = float(x)
        msg.pose.pose.position.y = float(y)
        msg.pose.pose.orientation.z = math.sin(float(yaw) / 2.0)
        msg.pose.pose.orientation.w = math.cos(float(yaw) / 2.0)
        # Tight covariance (high confidence)
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
