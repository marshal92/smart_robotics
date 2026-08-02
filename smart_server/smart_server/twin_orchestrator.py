#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from smart_interfaces.msg import SmartCommand # ДОБАВИЛИ ИМПОРТ

class TwinOrchestrator(Node):
    def __init__(self):
        super().__init__('twin_orchestrator')
        
        # СЛУШАЕМ НОВУЮ ЕДИНУЮ ШИНУ
        self.sub = self.create_subscription(SmartCommand, '/smart_command', self.command_cb, 10)
        
        # Передаем команду Тени по локальному топику (на сервере мост для этого не нужен)
        self.shadow_pub = self.create_publisher(String, '/shadow_command', 10)
        
        self.get_logger().info("[Server] Twin Orchestrator started! Waiting for /smart_command (target: operator)...")

    def command_cb(self, msg):
        # Реагируем ТОЛЬКО на команды для оператора/тени
        if msg.target_system != 'operator':
            return

        cmd = msg.command.lower()
        
        if cmd == 'execute':
            self.get_logger().info("[Server] EXECUTE command. Dispatching Shadow route...")
            shadow_msg = String()
            shadow_msg.data = 'execute'
            self.shadow_pub.publish(shadow_msg)
            
        elif cmd == 'clear':
            self.get_logger().warn("[Server] CLEAR command! Resetting Shadow.")
            shadow_msg = String()
            shadow_msg.data = 'clear'
            self.shadow_pub.publish(shadow_msg)

def main(args=None):
    rclpy.init(args=args)
    node = TwinOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Stopping Twin Orchestrator...")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()