#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav2_simple_commander.robot_navigator import BasicNavigator
from smart_interfaces.msg import SmartCommand

import json
import time
import math

class NavCoordinator(Node):
    def __init__(self):
        super().__init__('nav_coordinator')
        
        self.nav_queue = []
        self.active_task = None
        self.current_fsm_state = "UNKNOWN"
        self.bt_survival = "" 
        
        # Состояние скользящего окна вейпоинтов (Sliding Window)
        self.sw_active = False
        self.sw_poses = []
        self.sw_lap_nums = []
        self.sw_total_laps = 1
        self.sw_idx = 0
        self.sw_bt = ""
        self.sw_name = "route"
        self.sw_last_sent_indices = ()
        self.sw_window_size = 5     # макс. кол-во точек в скользящем окне
        self.sw_pass_radius = 0.75  # м — радиус зачёта промежуточной точки
        self.sw_min_end_dist = 1.80 # м — минимальная дистанция от робота до конца окна (должна быть > threshold_to_consider=1.4)
        self.resume_snapshot = None
        self.nav_paused = False

        # Позиция робота в map (обновляется из лёгкого /pose от SLAM и фидбека Nav2 без тяжёлого /tf)
        self.robot_x = None
        self.robot_y = None
        
        # Внутренний массив для накопления маршрута (когда точки добавляются по одной)
        self.route_accumulator = []

        self.create_subscription(SmartCommand, '/smart_command', self.cmd_cb, 10)
        self.create_subscription(String, '/fsm_status', self.fsm_cb, 10)
        self.create_subscription(PoseWithCovarianceStamped, '/pose', self.pose_cb, 5)
        self.status_pub = self.create_publisher(String, '/nav_status', 10)

        self.get_logger().info('Nav Coordinator activated (with Sliding Window). Awaiting commands.')

    def pose_cb(self, msg: PoseWithCovarianceStamped):
        self.robot_x = msg.pose.pose.position.x
        self.robot_y = msg.pose.pose.position.y

    def get_robot_xy(self):
        return self.robot_x, self.robot_y

    def save_resume_state(self):
        """Сохраняет текущую точку/маршрут и очередь, чтобы можно было нажать RESUME после отъезда."""
        if self.sw_active and self.sw_poses and self.sw_idx < len(self.sw_poses):
            self.resume_snapshot = {
                'type': 'waypoints',
                'poses': list(self.sw_poses),
                'lap_nums': list(self.sw_lap_nums),
                'total_laps': self.sw_total_laps,
                'bt': self.sw_bt,
                'name': self.sw_name,
                'start_idx': self.sw_idx,
                'remaining_queue': [t for t in self.nav_queue if t.get('type') != 'cancel']
            }
            cur_lap = self.sw_lap_nums[self.sw_idx] if self.sw_idx < len(self.sw_lap_nums) else self.sw_total_laps
            self.get_logger().info(
                f"[Resume] Saved route '{self.sw_name}' at WP {self.sw_idx + 1}/{len(self.sw_poses)} (Lap {cur_lap}/{self.sw_total_laps})."
            )
        elif self.active_task is not None and self.active_task.get('type') in ('go_to', 'rth'):
            self.resume_snapshot = {
                'type': 'single',
                'task': dict(self.active_task),
                'remaining_queue': [t for t in self.nav_queue if t.get('type') != 'cancel']
            }
            self.get_logger().info(f"[Resume] Saved point '{self.active_task.get('name', 'point')}' for resume.")

    def reset_sliding_window(self):
        self.sw_active = False
        self.sw_poses = []
        self.sw_lap_nums = []
        self.sw_idx = 0
        self.sw_last_sent_indices = ()

    def build_sliding_window(self, rx, ry):
        """Формирует окно из 1..3 точек вперёд так, чтобы конечная точка окна
        никогда не оказывалась рядом с роботом (иначе в MPPI отключается PathFollowCritic)."""
        n = len(self.sw_poses)
        if self.sw_idx >= n:
            return [], ()
        
        indices = [self.sw_idx]
        # Добавляем следующие точки в окно (до sw_window_size), только если они не замыкают кольцо прямо под роботом
        for offset in range(1, self.sw_window_size):
            cand_idx = self.sw_idx + offset
            if cand_idx >= n:
                break
            cand_p = self.sw_poses[cand_idx].pose.position
            prev_p = self.sw_poses[indices[-1]].pose.position
            # Не добавляем в текущее окно точку, если она совпадает с предыдущей
            if math.hypot(cand_p.x - prev_p.x, cand_p.y - prev_p.y) < 0.25:
                break
            if rx is not None and ry is not None:
                dist_to_robot = math.hypot(cand_p.x - rx, cand_p.y - ry)
                # Конец окна должен быть дальше 1.8 м от робота (у MPPI threshold_to_consider = 1.4 м)
                if dist_to_robot < self.sw_min_end_dist:
                    break
            indices.append(cand_idx)

        window_poses = [self.sw_poses[i] for i in indices]
        return window_poses, tuple(indices)

    def fsm_cb(self, msg):
        self.current_fsm_state = msg.data

    def cmd_cb(self, msg):
        # 1. Глобальные системные остановки
        if msg.target_system == 'system':
            cmd = msg.command.strip().lower()
            if cmd in ['stop', 'start_freeride', 'restart']:
                self.get_logger().warn("[System] Navigation disabled globally. Clearing queues.")
                self.nav_queue.clear()
                self.route_accumulator.clear()
                self.active_task = None
                self.reset_sliding_window()
            return

        # 2. Тактические команды навигации
        if msg.target_system == 'nav':
            action = msg.command.lower()
            
            payload = {}
            if msg.payload_json:
                try: payload = json.loads(msg.payload_json)
                except Exception as e: self.get_logger().error(f"JSON Error: {e}")

            # Cancel and RTH
            if action == "cancel":
                self.get_logger().info("Command CANCEL received. Stopping (state saved for RESUME).")
                self.save_resume_state()
                self.nav_queue.clear()
                self.reset_sliding_window()
                self.nav_paused = False
                self.nav_queue.append({'type': 'cancel'})
                self.active_task = None
                return

            if action == "resume":
                if self.sw_active:
                    self.get_logger().info("Route is already active.")
                    return
                if not self.resume_snapshot:
                    self.get_logger().warn("Nothing to resume! Send a route first.")
                    return
                snap = self.resume_snapshot
                self.resume_snapshot = None
                self.nav_paused = False
                self.nav_queue.clear()
                if snap['type'] == 'waypoints':
                    resume_task = {
                        'type': 'waypoints',
                        'poses': snap['poses'],
                        'lap_nums': snap['lap_nums'],
                        'bt': snap.get('bt', ''),
                        'total_laps': snap.get('total_laps', 1),
                        'name': snap.get('name', 'route'),
                        'start_idx': snap.get('start_idx', 0),
                    }
                    self.active_task = resume_task
                    self.nav_queue.append(resume_task)
                    self.nav_queue.extend(snap.get('remaining_queue', []))
                    cur_lap = snap['lap_nums'][snap['start_idx']] if snap['start_idx'] < len(snap['lap_nums']) else snap.get('total_laps', 1)
                    self.get_logger().info(
                        f"Command RESUME: continuing '{resume_task['name']}' from WP {snap['start_idx'] + 1}/{len(snap['poses'])} "
                        f"(Lap {cur_lap}/{resume_task['total_laps']})."
                    )
                elif snap['type'] == 'single':
                    t = snap['task']
                    self.active_task = t
                    self.nav_queue.append(t)
                    self.nav_queue.extend(snap.get('remaining_queue', []))
                    self.get_logger().info(f"Command RESUME: continuing point '{t.get('name', 'point')}'.")
                return
                
            if action == "rth":
                self.get_logger().info("Command RTH received. Returning to base!")
                goal_pose = self._create_pose(payload.get("x", 0.0), payload.get("y", 0.0), 0.0)
                self.nav_queue.clear()
                self.reset_sliding_window()
                self.nav_paused = False
                self.nav_queue.append({'type': 'rth', 'pose': goal_pose})
                return

            # Проверка безопасности (FSM)
            if self.current_fsm_state not in ["NORMAL", "DISABLED"]:
                self.get_logger().warn(f"Restricted: system in state {self.current_fsm_state}. Route rejected.")
                return

            # Одиночная поездка в точку
            if action in ["go_to", "go_to_with_bt"]:
                self.nav_paused = False
                laps = max(1, int(payload.get("laps", 1)))
                name = payload.get("name", "point")
                for lap in range(1, laps + 1):
                    goal_pose = self._create_pose(payload.get("x", 0.0), payload.get("y", 0.0), payload.get("yaw", 0.0))
                    task = {'type': 'go_to', 'pose': goal_pose, 'bt': payload.get("bt", ""), 'lap': lap, 'total_laps': laps, 'name': name}
                    self.active_task = task
                    self.nav_queue.append(task)
                self.get_logger().info(f"Queued point '{name}' (laps={laps}). Queue size: {len(self.nav_queue)}")

            # Массив точек (разворачиваем все круги в единый маршрут для скользящего окна)
            elif action == "waypoints":
                pts = payload.get("points", [])
                if not pts:
                    return
                self.nav_paused = False
                laps = max(1, int(payload.get("laps", 1)))
                name = payload.get("name", "route")
                all_poses = []
                lap_nums = []
                for lap in range(1, laps + 1):
                    for p in pts:
                        pose = self._create_pose(p[0], p[1], p[2] if len(p) > 2 else 0.0)
                        if all_poses:
                            prev = all_poses[-1].pose.position
                            cur = pose.pose.position
                            # Убираем дублирующуюся точку на стыке кругов, если последняя точка круга совпадает с первой
                            if math.hypot(cur.x - prev.x, cur.y - prev.y) < 0.20:
                                continue
                        all_poses.append(pose)
                        lap_nums.append(lap)
                task = {
                    'type': 'waypoints',
                    'poses': all_poses,
                    'lap_nums': lap_nums,
                    'bt': payload.get("bt", ""),
                    'total_laps': laps,
                    'name': name
                }
                self.active_task = task
                self.nav_queue.append(task)
                self.get_logger().info(f"Queued route '{name}' ({len(pts)} pts x {laps} laps -> {len(all_poses)} waypoints). Queue size: {len(self.nav_queue)}")

            # Добавить ОДНУ точку в локальный маршрут (для ручного построения)
            elif action == "add_to_route":
                pose = self._create_pose(payload.get("x", 0.0), payload.get("y", 0.0), payload.get("yaw", 0.0))
                self.route_accumulator.append(pose)
                self.get_logger().info(f"Point added to route. Total points in queue: {len(self.route_accumulator)}")

            # Запустить накопленный маршрут
            elif action == "start_route":
                if not self.route_accumulator:
                    self.get_logger().warn("Route is empty! Add points first.")
                    return
                poses = list(self.route_accumulator)
                task = {
                    'type': 'waypoints',
                    'poses': poses,
                    'lap_nums': [1] * len(poses),
                    'bt': payload.get("bt", ""),
                    'total_laps': 1,
                    'name': 'accumulated_route'
                }
                self.active_task = task
                self.nav_queue.append(task)
                self.get_logger().info(f"Starting accumulated route with {len(self.route_accumulator)} points.")
                self.route_accumulator.clear() # Очищаем накопитель после запуска

            # Очистить накопленный маршрут
            elif action == "clear_route":
                self.route_accumulator.clear()
                self.get_logger().info("Accumulated route cleared.")


    def _create_pose(self, x, y, yaw):
        """Вспомогательная функция создания PoseStamped"""
        p = PoseStamped()
        p.header.frame_id = 'map'
        p.pose.position.x = float(x)
        p.pose.position.y = float(y)
        p.pose.orientation.z = math.sin(float(yaw) / 2.0)
        p.pose.orientation.w = math.cos(float(yaw) / 2.0)
        return p


def _send_sliding_window(node, navigator, rx, ry):
    """Формирует и отправляет текущее скользящее окно точек в Nav2."""
    window_poses, indices = node.build_sliding_window(rx, ry)
    if not window_poses or indices == node.sw_last_sent_indices:
        return False
    now_msg = navigator.get_clock().now().to_msg()
    for p in window_poses:
        p.header.stamp = now_msg
    if node.sw_bt:
        navigator.goThroughPoses(window_poses, behavior_tree=node.sw_bt)
    else:
        navigator.goThroughPoses(window_poses)
    node.sw_last_sent_indices = indices
    cur_lap = node.sw_lap_nums[node.sw_idx] if node.sw_idx < len(node.sw_lap_nums) else node.sw_total_laps
    idx_human = [i + 1 for i in indices]
    node.get_logger().info(
        f"[SlidingWindow] '{node.sw_name}' Lap {cur_lap}/{node.sw_total_laps} | "
        f"Window WPs {idx_human}/{len(node.sw_poses)}"
    )
    return True


def main(args=None):
    rclpy.init(args=args)
    node = NavCoordinator()
    navigator = BasicNavigator()
    
    try:
        last_pub = 0.0
        nav_state = "IDLE"
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            rclpy.spin_once(navigator, timeout_sec=0.01)
            time.sleep(0.02)

            # Обновляем координаты робота из штатного фидбека Nav2 (C++ bt_navigator)
            fb = navigator.getFeedback()
            if fb is not None and hasattr(fb, 'current_pose'):
                cp = fb.current_pose.pose.position
                if cp.x != 0.0 or cp.y != 0.0:
                    node.robot_x = cp.x
                    node.robot_y = cp.y

            # 1. Обновление скользящего окна вейпоинтов по текущей позиции робота
            if node.sw_active and node.sw_poses:
                rx, ry = node.get_robot_xy()
                if rx is not None and node.sw_idx < len(node.sw_poses) - 1:
                    advanced = False
                    while node.sw_idx < len(node.sw_poses) - 1:
                        target_p = node.sw_poses[node.sw_idx].pose.position
                        dist = math.hypot(target_p.x - rx, target_p.y - ry)
                        if dist <= node.sw_pass_radius:
                            node.sw_idx += 1
                            advanced = True
                        else:
                            break
                    if advanced:
                        _send_sliding_window(node, navigator, rx, ry)

            # 2. Проверка состояния задачи в Nav2
            if navigator.result_future:
                if not navigator.result_future.done():
                    nav_state = "MOVING"
                else:
                    res = navigator.result_future.result()
                    if res:
                        if res.status == 4: # SUCCEEDED
                            if node.sw_active and node.sw_poses:
                                last_sent = node.sw_last_sent_indices[-1] if node.sw_last_sent_indices else node.sw_idx
                                if last_sent < len(node.sw_poses) - 1:
                                    node.sw_idx = last_sent + 1
                                    rx, ry = node.get_robot_xy()
                                    _send_sliding_window(node, navigator, rx, ry)
                                    nav_state = "MOVING"
                                else:
                                    node.get_logger().info(
                                        f"Route '{node.sw_name}' FINISHED ({len(node.sw_poses)} WPs, {node.sw_total_laps} laps)."
                                    )
                                    node.reset_sliding_window()
                                    navigator.result_future = None
                                    nav_state = "SUCCEEDED"
                            else:
                                navigator.result_future = None
                                nav_state = "SUCCEEDED"
                        elif res.status == 5: # CANCELED
                            node.reset_sliding_window()
                            navigator.result_future = None
                            nav_state = "CANCELED"
                        elif res.status == 6: # ABORTED
                            node.get_logger().warn("Nav2 task ABORTED! State saved — drive away and press RESUME to continue.")
                            node.save_resume_state()
                            node.reset_sliding_window()
                            node.nav_paused = True
                            navigator.result_future = None
                            nav_state = "ABORTED"
                        else:
                            navigator.result_future = None
                            nav_state = "IDLE"
            elif nav_state == "MOVING":
                nav_state = "IDLE"

            if time.time() - last_pub > 0.2:
                node.status_pub.publish(String(data=nav_state))
                last_pub = time.time()
            
            if node.nav_queue:
                if node.nav_queue[0]['type'] == 'cancel':
                    node.nav_queue.pop(0)
                    node.reset_sliding_window()
                    if nav_state == "MOVING":
                        navigator.cancelTask()
                        time.sleep(0.5)
                    navigator.result_future = None
                    nav_state = "CANCELED"
                    node.active_task = None
                    continue

                if nav_state == "MOVING" or node.sw_active or node.nav_paused:
                    continue 

                nav_is_alive = navigator.nav_to_pose_client.wait_for_server(timeout_sec=0.1)
                if not nav_is_alive:
                    node.get_logger().warn("Nav2 deactivated. Waiting...", throttle_duration_sec=5.0)
                    continue 
                
                task = node.nav_queue.pop(0) 
                node.active_task = task
                cmd = task['type']
                lap_info = f" [Lap {task.get('lap', 1)}/{task.get('total_laps', 1)}]" if task.get('total_laps', 1) > 1 else ""
                node.get_logger().info(f"Starting task '{task.get('name', cmd)}'{lap_info}. Remaining in queue: {len(node.nav_queue)}")
                
                try:
                    # Одиночная точка
                    if cmd == 'go_to':
                        pose = task['pose']
                        pose.header.stamp = navigator.get_clock().now().to_msg()
                        bt = task.get('bt', '')
                        if bt: navigator.goToPose(pose, behavior_tree=bt)
                        else: navigator.goToPose(pose) 
                    
                    # МАРШРУТ со скользящим окном вейпоинтов (Sliding Window)
                    elif cmd == 'waypoints':
                        poses = task['poses']
                        if not poses:
                            continue
                        node.sw_active = True
                        node.sw_poses = poses
                        node.sw_lap_nums = task.get('lap_nums', [1] * len(poses))
                        node.sw_total_laps = task.get('total_laps', 1)
                        node.sw_bt = task.get('bt', '')
                        node.sw_name = task.get('name', 'route')
                        node.sw_idx = int(task.get('start_idx', 0))
                        node.sw_last_sent_indices = ()

                        rx, ry = node.get_robot_xy()
                        # Если стартуем с 0-й точки и робот уже стоит на ней (< 0.65 м), сразу целимся во 2-ю точку
                        if node.sw_idx == 0 and rx is not None and len(poses) > 1:
                            p0 = poses[0].pose.position
                            d0 = math.hypot(p0.x - rx, p0.y - ry)
                            if d0 < 0.65:
                                node.sw_idx = 1
                                node.get_logger().info(
                                    f"[SlidingWindow] Robot already at WP 1 (d={d0:.2f}m), starting from WP 2/{len(poses)}"
                                )
                        _send_sliding_window(node, navigator, rx, ry)
                            
                    # Домой
                    elif cmd == 'rth':
                        pose = task['pose']
                        pose.header.stamp = navigator.get_clock().now().to_msg()
                        if node.bt_survival: navigator.goToPose(pose, behavior_tree=node.bt_survival)
                        else: navigator.goToPose(pose) 
                        
                except Exception as e:
                    node.get_logger().error(f"Error Action Client: {e}")
                    node.reset_sliding_window()

    except KeyboardInterrupt:
        node.get_logger().info("Stopping Nav Coordinator...")
    finally:
        navigator.lifecycleShutdown()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()