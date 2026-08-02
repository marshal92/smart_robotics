#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
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
        
        # Внутренний массив для накопления маршрута (когда точки добавляются по одной)
        self.route_accumulator = []

        self.create_subscription(SmartCommand, '/smart_command', self.cmd_cb, 10)
        self.create_subscription(String, '/fsm_status', self.fsm_cb, 10)
        self.status_pub = self.create_publisher(String, '/nav_status', 10)

        self.get_logger().info('Nav Coordinator activated. Awaiting commands.')

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
                self.get_logger().info("Command CANCEL received. Stopping.")
                self.nav_queue.clear()
                self.nav_queue.append({'type': 'cancel'})
                self.active_task = None
                return
                
            if action == "rth":
                self.get_logger().info("Command RTH received. Returning to base!")
                goal_pose = self._create_pose(payload.get("x", 0.0), payload.get("y", 0.0), 0.0)
                self.nav_queue.clear()
                self.nav_queue.append({'type': 'rth', 'pose': goal_pose})
                return

            # Проверка безопасности (FSM)
            if self.current_fsm_state not in ["NORMAL", "DISABLED"]:
                self.get_logger().warn(f"Restricted: system in state {self.current_fsm_state}. Route rejected.")
                return

            # Одиночная поездка в точку
            if action in ["go_to", "go_to_with_bt"]:
                goal_pose = self._create_pose(payload.get("x", 0.0), payload.get("y", 0.0), payload.get("yaw", 0.0))
                task = {'type': 'go_to', 'pose': goal_pose, 'bt': payload.get("bt", "")}
                self.active_task = task
                self.nav_queue.append(task)
                self.get_logger().info(f"Going to single point: X={goal_pose.pose.position.x}, Y={goal_pose.pose.position.y}")

            # Массив точек (например, прилетает целиком от Shadow)
            elif action == "waypoints":
                pts = payload.get("points", [])
                poses = [self._create_pose(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in pts]
                task = {'type': 'waypoints', 'poses': poses, 'bt': payload.get("bt", "")}
                self.active_task = task
                self.nav_queue.append(task)
                self.get_logger().info(f"Received Route of {len(poses)} points from Server/Shadow.")

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
                task = {'type': 'waypoints', 'poses': list(self.route_accumulator), 'bt': payload.get("bt", "")}
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


def main(args=None):
    rclpy.init(args=args)
    node = NavCoordinator()
    navigator = BasicNavigator()
    
    try:
        last_pub = 0.0
        nav_state = "IDLE"
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            # Spin navigator so action client processes callbacks
            rclpy.spin_once(navigator, timeout_sec=0.01)

            # Check navigation state
            if navigator.result_future:
                if not navigator.result_future.done():
                    nav_state = "MOVING"
                else:
                    res = navigator.result_future.result()
                    if res:
                        if res.status == 4: # SUCCEEDED
                            nav_state = "SUCCEEDED"
                        elif res.status == 5: # CANCELED
                            nav_state = "CANCELED"
                        elif res.status == 6: # ABORTED
                            nav_state = "ABORTED"
                        else:
                            nav_state = "IDLE"
            else:
                nav_state = "IDLE"

            if time.time() - last_pub > 0.2:
                node.status_pub.publish(String(data=nav_state))
                last_pub = time.time()
            
            if node.nav_queue:
                if node.nav_queue[0]['type'] == 'cancel':
                    node.nav_queue.pop(0)
                    if nav_state == "MOVING":
                        navigator.cancelTask()
                        time.sleep(0.5)
                    node.active_task = None
                    continue

                if nav_state == "MOVING":
                    continue 

                nav_is_alive = navigator.nav_to_pose_client.wait_for_server(timeout_sec=0.1)
                if not nav_is_alive:
                    node.get_logger().warn("Nav2 deactivated. Waiting...", throttle_duration_sec=5.0)
                    continue 
                
                task = node.nav_queue.pop(0) 
                cmd = task['type']
                
                try:
                    # Одиночная точка
                    if cmd == 'go_to':
                        pose = task['pose']
                        pose.header.stamp = navigator.get_clock().now().to_msg()
                        bt = task.get('bt', '')
                        if bt: navigator.goToPose(pose, behavior_tree=bt)
                        else: navigator.goToPose(pose) 
                    
                    # МАРШРУТ (Массив точек) - ЭТОГО НЕ ХВАТАЛО
                    elif cmd == 'waypoints':
                        poses = task['poses']
                        for p in poses: 
                            p.header.stamp = navigator.get_clock().now().to_msg()
                        bt = task.get('bt', '')
                        if bt: navigator.goThroughPoses(poses, behavior_tree=bt)
                        else: navigator.goThroughPoses(poses)
                            
                    # Домой
                    elif cmd == 'rth':
                        pose = task['pose']
                        pose.header.stamp = navigator.get_clock().now().to_msg()
                        if node.bt_survival: navigator.goToPose(pose, behavior_tree=node.bt_survival)
                        else: navigator.goToPose(pose) 
                        
                except Exception as e:
                    node.get_logger().error(f"Error Action Client: {e}")

    except KeyboardInterrupt:
        node.get_logger().info("Stopping Nav Coordinator...")
    finally:
        navigator.lifecycleShutdown()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()