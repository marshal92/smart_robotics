#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator
import json
import time
import math

class NavCoordinator(Node):
    def __init__(self):
        super().__init__('nav_coordinator')
        
        self.nav_queue = []
        self.active_task = None
        self.current_fsm_state = "UNKNOWN"
        self.bt_survival = "" # Here I can later specify the path to the evacuation tree

        self.create_subscription(String, '/tactical_command', self.tactical_cb, 10)
        self.create_subscription(String, '/system_command', self.system_cb, 10)
        self.create_subscription(String, '/fsm_status', self.fsm_cb, 10)

        self.get_logger().info('Nav Coordinator activated. Awaiting commands.')

    def fsm_cb(self, msg):
        self.current_fsm_state = msg.data

    def system_cb(self, msg):
        cmd = msg.data.strip().lower().split(':')[0]
        if cmd in ['stop', 'start_freeride', 'restart']:
            self.get_logger().warn("[System] Navigation disabled globally. Clearing queues.")
            self.nav_queue.clear()
            self.active_task = None

    def tactical_cb(self, msg):
        try:
            payload = json.loads(msg.data)
            action = payload.get("action")

            # Cancel and Return to Home are allowed ALWAYS
            if action == "cancel":
                self.get_logger().info("Command CANCEL received. Stopping.")
                self.nav_queue.clear()
                self.nav_queue.append({'type': 'cancel'})
                self.active_task = None
                return
                
            if action == "rth":
                self.get_logger().info("Command RTH received. Returning to base!")
                goal_pose = PoseStamped()
                goal_pose.header.frame_id = 'map'
                goal_pose.pose.position.x = float(payload.get("x", 0.0))
                goal_pose.pose.position.y = float(payload.get("y", 0.0))
                goal_pose.pose.orientation.w = 1.0
                self.nav_queue.clear()
                self.nav_queue.append({'type': 'rth', 'pose': goal_pose})
                return

            # Common routes are allowed ONLY if FSM is normal
            if self.current_fsm_state != "NORMAL":
                self.get_logger().warn(f"Restricted: system in state {self.current_fsm_state}. Route rejected.")
                return

            if action in ["go_to", "go_to_with_bt"]:
                yaw = float(payload.get("yaw", 0.0))
                goal_pose = PoseStamped()
                goal_pose.header.frame_id = 'map'
                goal_pose.pose.position.x = float(payload.get("x", 0.0))
                goal_pose.pose.position.y = float(payload.get("y", 0.0))
                goal_pose.pose.orientation.z = math.sin(yaw / 2.0)
                goal_pose.pose.orientation.w = math.cos(yaw / 2.0)
            
                task = {'type': 'go_to', 'pose': goal_pose, 'bt': payload.get("bt", "")}
                self.active_task = task
                self.nav_queue.append(task)
                self.get_logger().info(f"Route added: X={goal_pose.pose.position.x}, Y={goal_pose.pose.position.y}")

        except Exception as e:
            self.get_logger().error(f"Error parsing JSON: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = NavCoordinator()
    navigator = BasicNavigator()
    
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            
            if node.nav_queue:
                if node.nav_queue[0]['type'] == 'cancel':
                    node.nav_queue.pop(0)
                    if not navigator.isTaskComplete():
                        navigator.cancelTask()
                        time.sleep(0.5)
                    node.active_task = None
                    continue

                if not navigator.isTaskComplete():
                    continue 

                nav_is_alive = navigator.nav_to_pose_client.wait_for_server(timeout_sec=0.1)
                if not nav_is_alive:
                    node.get_logger().warn("Nav2 deactivated. Waiting...", throttle_duration_sec=5.0)
                    continue 
                
                task = node.nav_queue.pop(0) 
                cmd = task['type']
                
                try:
                    if cmd == 'go_to':
                        pose = task['pose']
                        pose.header.stamp = navigator.get_clock().now().to_msg()
                        bt = task.get('bt', '')
                        if bt: navigator.goToPose(pose, behavior_tree=bt)
                        else: navigator.goToPose(pose) 
                            
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