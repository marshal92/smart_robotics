#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty, String
from geometry_msgs.msg import PoseStamped
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from nav2_simple_commander.robot_navigator import BasicNavigator
from enum import Enum
import json
import threading
import math
import time

class SystemState(Enum):
    NORMAL = 1          
    WARNING = 2         
    EVACUATING = 3      
    SAFE_HOLD = 4       

class MissionControl(Node):
    def __init__(self):
        super().__init__('mission_control')
        
        # --- ТАЙМИНГИ ПОТЕРИ СВЯЗИ ---
        self.timeout_warning = 5.0      
        self.timeout_evacuate = 25.0    
        self.bt_survival = ''           
        
        # --- ФИЛЬТРЫ СТАБИЛЬНОСТИ ---
        self.stability_required = 3.0    # Сек. непрерывного сигнала для выхода из тревоги
        self.evacuation_lockout = 10.0   # Сек. "глухоты" при старте эвакуации
        
        self.current_state = SystemState.NORMAL
        self.last_heartbeat = self.get_clock().now().nanoseconds / 1e9
        self.first_heartbeat_received = False 
        
        self.good_signal_start = None    
        self.evacuation_start_time = 0.0 
        
        self.active_task = None         
        self.deployed_tools = set()     
        self.nav_queue = []     

        heartbeat_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1
        )

        self.create_subscription(Empty, '/operator_heartbeat', self.heartbeat_cb, heartbeat_qos)
        self.create_subscription(PoseStamped, '/goal_pose', self.goal_cb, 10)
        self.create_subscription(String, '/tactical_command', self.tactical_cb, 10)
        self.create_subscription(String, '/operator_command', self.operator_cb, 10)
        
        # Подписываемся на команды системы, чтобы знать, когда убили Nav2
        self.create_subscription(String, '/system_command', self.system_cb, 10)

        self.get_logger().info('[Mission Control] Инициализация. Ждем первый пульс...')

    # ================= КОЛЛБЭКИ =================

    def system_cb(self, msg):
        """Отслеживает глобальные остановки системы от mission_manager"""
        cmd = msg.data.strip().lower().split(':')[0]
        if cmd in ['stop', 'start_freeride', 'restart']:
            self.get_logger().warn("[System] Навигация отключена глобально. Очистка очередей.")
            self.nav_queue.clear()
            self.active_task = None

    def heartbeat_cb(self, msg):
        if not self.first_heartbeat_received:
            self.get_logger().info('Первый пульс получен. FSM Активирована.')
            self.first_heartbeat_received = True
        self.last_heartbeat = self.get_clock().now().nanoseconds / 1e9

    def goal_cb(self, msg):
        if self.current_state == SystemState.NORMAL:
            task = {'type': 'go_to', 'pose': msg, 'bt': ''}
            self.active_task = task
            self.nav_queue.append(task)

    def operator_cb(self, msg):
        cmd = msg.data.upper()
        if cmd == "RESUME":
            if self.current_state == SystemState.SAFE_HOLD:
                self.get_logger().info('[OPERATOR] Команда RESUME принята. Система разблокирована.')
                self.transition_to(SystemState.NORMAL)
                if self.active_task:
                    self.get_logger().info('Восстановление прерванного маршрута...')
                    self.nav_queue.append(self.active_task)
            else:
                 self.get_logger().info(f'RESUME игнорируется. Текущий статус: {self.current_state.name}')

    def tactical_cb(self, msg):
        try:
            payload = json.loads(msg.data)
            action = payload.get("action")

            if action == "cancel":
                self.get_logger().info("Команда CANCEL. Остановка навигации.")
                self.nav_queue.clear()
                self.nav_queue.append({'type': 'cancel'})
                self.active_task = None
                return

            if action == "mock_sample":
                self.get_logger().info("Запуск подпрограммы взятия пробы.")
                threading.Thread(target=self._execute_mock_sample, daemon=True).start()
                return

            if self.current_state != SystemState.NORMAL:
                self.get_logger().warn(f"Запрещено: система в состоянии {self.current_state.name}. Отклонено.")
                return

            if action in ["go_to", "go_to_with_bt"]:
                x = float(payload.get("x", 0.0))
                y = float(payload.get("y", 0.0))
                yaw = float(payload.get("yaw", 0.0))
                bt_xml = payload.get("bt", "")
                
                goal_pose = PoseStamped()
                goal_pose.header.frame_id = 'map'
                goal_pose.pose.position.x = x
                goal_pose.pose.position.y = y
                goal_pose.pose.orientation.z = math.sin(yaw / 2.0)
                goal_pose.pose.orientation.w = math.cos(yaw / 2.0)
            
                task = {'type': 'go_to', 'pose': goal_pose, 'bt': bt_xml}
                self.active_task = task
                self.nav_queue.append(task)
                self.get_logger().info(f"📍 Транзит добавлен: X={x}, Y={y}")

            elif action == "waypoints":
                pts = payload.get("points", [])
                poses = []
                for p in pts:
                    pose = PoseStamped()
                    pose.header.frame_id = 'map'
                    pose.pose.position.x = float(p[0])
                    pose.pose.position.y = float(p[1])
                    yaw = float(p[2]) if len(p) > 2 else 0.0
                    pose.pose.orientation.z = math.sin(yaw / 2.0)
                    pose.pose.orientation.w = math.cos(yaw / 2.0)
                    poses.append(pose)
                
                task = {'type': 'waypoints', 'poses': poses, 'bt': payload.get("bt", "")}
                self.active_task = task
                self.nav_queue.append(task)
                self.get_logger().info(f"📍 Сплайн из {len(poses)} точек добавлен в очередь.")

        except Exception as e:
            self.get_logger().error(f"Ошибка парсинга JSON: {e}")

    def _execute_mock_sample(self):
        tool_name = "lfcm_drill"
        self.deployed_tools.add(tool_name) 
        try:
            self.get_logger().info("[Payload]: Бурение начато...")
            time.sleep(2.0)
            self.get_logger().info("[Payload]: Калибровка...")
            time.sleep(3.0)
            self.get_logger().info("[Payload]: Проба изолирована.")
        finally:
            self.deployed_tools.discard(tool_name) 

    def transition_to(self, new_state):
        if self.current_state == new_state: return

        old_state = self.current_state
        self.current_state = new_state
        now = self.get_clock().now().nanoseconds / 1e9
        
        self.get_logger().info(f'[FSM] Переход: {old_state.name} -> {new_state.name}')

        if new_state == SystemState.WARNING:
            self.get_logger().warn('[Connection] ПОТЕРЯ СИГНАЛА (>5с)! Экстренное торможение.')
            self.nav_queue.clear()
            self.nav_queue.append({'type': 'cancel'})

        elif new_state == SystemState.EVACUATING:
            self.get_logger().error('[Connection] КРИТИЧЕСКИЙ СБОЙ (>25с)! Запуск эвакуации.')
            self.evacuation_start_time = now 
            self.nav_queue.clear()
            self.nav_queue.append({'type': 'cancel'})
            
            home_pose = PoseStamped()
            home_pose.header.frame_id = 'map'
            home_pose.pose.orientation.w = 1.0
            self.nav_queue.append({'type': 'rth', 'pose': home_pose})
            
        elif new_state == SystemState.SAFE_HOLD:
            self.get_logger().warn('Сигнал стабилизирован. Робот ЗАБЛОКИРОВАН. Нажмите RESUME.')
            self.nav_queue.clear()
            self.nav_queue.append({'type': 'cancel'})

# ================= ГЛАВНЫЙ ЦИКЛ =================
def main(args=None):
    rclpy.init(args=args)
    node = MissionControl()
    navigator = BasicNavigator()
    
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            
            # --- 1. ВЫПОЛНЕНИЕ НАВИГАЦИИ ---
            if node.nav_queue:
                task = node.nav_queue[0] # Смотрим на задачу, не удаляя
                cmd = task['type']
                
                # ПРОБЛЕМА БЕССМЕРТНОГО МОЗГА: Проверяем жив ли Nav2
                nav_is_alive = navigator.nav_to_pose_client.wait_for_server(timeout_sec=0.1)
                
                if not nav_is_alive and cmd != 'cancel':
                    node.get_logger().warn("Навигационный стек (Nav2) отключен. Задача сброшена.", throttle_duration_sec=5.0)
                    node.nav_queue.pop(0)
                    node.active_task = None
                    continue # Пропускаем цикл, ждем пока Nav2 поднимется
                
                # Если дошли сюда, Nav2 жив или это просто отмена
                task = node.nav_queue.pop(0) # Теперь удаляем из очереди
                
                try:
                    if cmd == 'cancel':
                        if nav_is_alive and not navigator.isTaskComplete():
                            navigator.cancelTask()
                            time.sleep(0.5) 
                            
                    elif cmd == 'go_to':
                        pose = task['pose']
                        pose.header.stamp = navigator.get_clock().now().to_msg()
                        bt = task.get('bt', '')
                        if bt: navigator.goToPose(pose, behavior_tree=bt)
                        else: navigator.goToPose(pose) 
                            
                    elif cmd == 'waypoints':
                        poses = task['poses']
                        for p in poses: p.header.stamp = navigator.get_clock().now().to_msg()
                        bt = task.get('bt', '')
                        if bt: navigator.goThroughPoses(poses, behavior_tree=bt)
                        else: navigator.goThroughPoses(poses) 
                            
                    elif cmd == 'rth':
                        pose = task['pose']
                        pose.header.stamp = navigator.get_clock().now().to_msg()
                        if node.bt_survival: navigator.goToPose(pose, behavior_tree=node.bt_survival)
                        else: navigator.goToPose(pose) 
                except Exception as e:
                    node.get_logger().error(f"Ошибка Action Client: {e}")

            # --- 2. ЛОГИКА БЕЗОПАСНОСТИ И СТАБИЛЬНОСТИ ---
            if not node.first_heartbeat_received:
                continue

            now = node.get_clock().now().nanoseconds / 1e9
            elapsed = now - node.last_heartbeat

            if node.current_state == SystemState.EVACUATING and (now - node.evacuation_start_time) < node.evacuation_lockout:
                node.good_signal_start = None
                continue 

            if elapsed < node.timeout_warning:
                if node.good_signal_start is None:
                    node.good_signal_start = now 
            else:
                node.good_signal_start = None    

            if elapsed >= node.timeout_evacuate:
                if len(node.deployed_tools) > 0:
                    if node.current_state != SystemState.WARNING: 
                        node.transition_to(SystemState.WARNING) 
                        node.get_logger().error('Отложенная эвакуация: Бур в породе!')
                    continue
                if node.current_state != SystemState.EVACUATING:
                    node.transition_to(SystemState.EVACUATING)

            elif elapsed >= node.timeout_warning:
                if node.current_state in [SystemState.NORMAL, SystemState.SAFE_HOLD]:
                    node.transition_to(SystemState.WARNING)

            elif node.good_signal_start is not None and (now - node.good_signal_start) >= node.stability_required:
                if node.current_state in [SystemState.WARNING, SystemState.EVACUATING]:
                    node.transition_to(SystemState.SAFE_HOLD)
                    
    except KeyboardInterrupt:
        node.get_logger().info("Остановка Mission Control...")
    finally:
        navigator.lifecycleShutdown()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()