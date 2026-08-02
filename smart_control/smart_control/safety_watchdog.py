#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty, String
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from enum import Enum
from smart_interfaces.msg import SmartCommand

import json
import time

class SystemState(Enum):
    NORMAL = 1          
    WARNING = 2         
    EVACUATING = 3      
    SAFE_HOLD = 4       

class SafetyWatchdog(Node):
    def __init__(self):
        super().__init__('safety_watchdog')
        
        self.declare_parameter('require_heartbeat', True)
        self.require_heartbeat = self.get_parameter('require_heartbeat').value
        
        # Timeouts (in seconds)
        self.timeout_warning = 5.0      
        self.timeout_evacuate = 25.0    
        self.stability_required = 3.0    
        self.evacuation_lockout = 10.0   
        
        self.current_state = SystemState.NORMAL
        self.last_heartbeat = self.get_clock().now().nanoseconds / 1e9
        self.first_heartbeat_received = not self.require_heartbeat
        
        self.good_signal_start = None    
        self.evacuation_start_time = 0.0 
        self.deployed_tools = set()     

        # Publishers
        self.fsm_pub = self.create_publisher(String, '/fsm_status', 10)
        self.cmd_pub = self.create_publisher(SmartCommand, '/smart_command', 10)
        #self.tactical_pub = self.create_publisher(String, '/tactical_command', 10)

        # Subscriptions
        heartbeat_qos = QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT, history=QoSHistoryPolicy.KEEP_LAST, depth=1)
        self.create_subscription(Empty, '/operator_heartbeat', self.heartbeat_cb, heartbeat_qos)
        self.create_subscription(String, '/payload/status', self.payload_status_cb, 10)
        self.create_subscription(SmartCommand, '/smart_command', self.operator_cb, 10)
        #self.create_subscription(String, '/operator_command', self.operator_cb, 10)

        # Main check loop (10 Hz)
        self.create_timer(0.1, self.fsm_loop)

        self.get_logger().info(f"Safety Watchdog activated. Heartbeat requirement: {self.require_heartbeat}")

    def heartbeat_cb(self, msg):
        if not self.first_heartbeat_received:
            self.get_logger().info('First heartbeat received. FSM activated.')
            self.first_heartbeat_received = True
        self.last_heartbeat = self.get_clock().now().nanoseconds / 1e9

    def payload_status_cb(self, msg):
        try:
            data = json.loads(msg.data)
            self.deployed_tools = set(data.get("active_tools", []))
        except Exception as e:
            self.get_logger().error(f"Error processing payload status: {e}")

    def operator_cb(self, msg):
        if msg.target_system == 'operator' and msg.command.upper() == "RESUME":
            if self.current_state == SystemState.SAFE_HOLD:
                self.get_logger().info('[OPERATOR] Command RESUME received. System unlocked.')
                self.transition_to(SystemState.NORMAL)
            else:
                 self.get_logger().info(f'RESUME ignored. Current state: {self.current_state.name}')
        elif msg.target_system == 'system':
            if msg.command == 'watchdog_on':
                self.require_heartbeat = True
                self.first_heartbeat_received = False
                self.get_logger().info('Watchdog ARMED by command. Waiting for first pulse...')
            elif msg.command == 'watchdog_off':
                self.require_heartbeat = False
                self.first_heartbeat_received = False
                self.transition_to(SystemState.NORMAL)
                self.get_logger().info('Watchdog DISARMED by command.')

    def transition_to(self, new_state):
        if self.current_state == new_state: return
        old_state = self.current_state
        self.current_state = new_state
        now = self.get_clock().now().nanoseconds / 1e9
        
        self.get_logger().info(f'[FSM] Transition: {old_state.name} -> {new_state.name}')

        if new_state == SystemState.WARNING:
            self.get_logger().warn('SIGNAL LOST! Emergency braking.')
            self.cmd_pub.publish(SmartCommand(target_system='nav', command='cancel'))

        elif new_state == SystemState.EVACUATING:
            self.get_logger().error('CRITICAL FAILURE! Initiating evacuation.')
            self.evacuation_start_time = now 
            self.cmd_pub.publish(SmartCommand(target_system='nav', command='cancel'))
            time.sleep(0.5)
            # Экстренный RTH
            payload = json.dumps({"x": 0.0, "y": 0.0, "yaw": 0.0})
            self.cmd_pub.publish(SmartCommand(target_system='nav', command='rth', payload_json=payload))
            
        elif new_state == SystemState.SAFE_HOLD:
            self.get_logger().warn('SIGNAL STABILIZED. ROBOT LOCKED. PRESS RESUME.')
            self.cmd_pub.publish(SmartCommand(target_system='nav', command='cancel'))

    def fsm_loop(self):
        if not self.require_heartbeat or not self.first_heartbeat_received:
            self.fsm_pub.publish(String(data="DISABLED"))
            return
            
        self.fsm_pub.publish(String(data=self.current_state.name))

        now = self.get_clock().now().nanoseconds / 1e9
        elapsed = now - self.last_heartbeat

        if self.current_state == SystemState.EVACUATING and (now - self.evacuation_start_time) < self.evacuation_lockout:
            self.good_signal_start = None
            return 

        if elapsed < self.timeout_warning:
            if self.good_signal_start is None:
                self.good_signal_start = now 
        else:
            self.good_signal_start = None    

        if elapsed >= self.timeout_evacuate:
            if len(self.deployed_tools) > 0:
                if self.current_state != SystemState.WARNING: 
                    self.transition_to(SystemState.WARNING) 
                    self.get_logger().error('Delayed evacuation: Equipment in operational position!')
                return
            if self.current_state != SystemState.EVACUATING:
                self.transition_to(SystemState.EVACUATING)

        elif elapsed >= self.timeout_warning:
            if self.current_state in [SystemState.NORMAL, SystemState.SAFE_HOLD]:
                self.transition_to(SystemState.WARNING)

        elif self.good_signal_start is not None and (now - self.good_signal_start) >= self.stability_required:
            if self.current_state in [SystemState.WARNING, SystemState.EVACUATING]:
                self.transition_to(SystemState.SAFE_HOLD)

def main(args=None):
    rclpy.init(args=args)
    node = SafetyWatchdog()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()