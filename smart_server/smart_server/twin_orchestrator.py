#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from smart_interfaces.msg import SmartCommand # ДОБАВИЛИ ИМПОРТ
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue

class TwinOrchestrator(Node):
    def __init__(self):
        super().__init__('twin_orchestrator')
        
        # СЛУШАЕМ НОВУЮ ЕДИНУЮ ШИНУ
        self.sub = self.create_subscription(SmartCommand, '/smart_command', self.command_cb, 10)
        
        # Передаем команду Тени по локальному топику (на сервере мост для этого не нужен)
        self.shadow_pub = self.create_publisher(String, '/shadow_command', 10)
        self.shadow_param_cli = self.create_client(SetParameters, '/shadow_teleop/set_parameters')
        
        self.get_logger().info("[Server] Twin Orchestrator started! Waiting for /smart_command (target: operator)...")

    def _set_shadow_active(self, is_active: bool):
        if self.shadow_param_cli.wait_for_service(timeout_sec=1.0):
            req = SetParameters.Request()
            param = Parameter(
                name='is_active',
                value=ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=is_active)
            )
            req.parameters.append(param)
            self.shadow_param_cli.call_async(req)
            self.get_logger().info(f"[Server] Shadow Teleop set to: {'ON' if is_active else 'OFF'}")

    def command_cb(self, msg):
        cmd = msg.command.strip().lower()

        if msg.target_system == 'system' and cmd in ('shadow_on', 'shadow_off'):
            self._set_shadow_active(cmd == 'shadow_on')
            return

        # Реагируем ТОЛЬКО на команды для оператора/тени
        if msg.target_system != 'operator':
            return
        
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