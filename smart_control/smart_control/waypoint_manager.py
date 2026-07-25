#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray
import json
import os
import math

class WaypointManager(Node):
    def __init__(self):
        super().__init__('waypoint_manager')
        
        self.wp_list_pub = self.create_publisher(String, '/waypoints_list', 10)
        self.tactical_pub = self.create_publisher(String, '/tactical_command', 10)
        self.marker_pub = self.create_publisher(MarkerArray, '/smart_waypoints_markers', 10)
        
        self.create_subscription(String, '/waypoint_command', self.command_cb, 10)
        
        self.waypoints_dir = os.path.expanduser('~/.ros/smart_data')
        os.makedirs(self.waypoints_dir, exist_ok=True)
        self.waypoints_db_file = os.path.join(self.waypoints_dir, 'waypoints.json')
        self.waypoints = self.load_waypoints()
        
        self.create_timer(2.0, self.sync_routine)
        self.get_logger().info('Waypoint Manager activated. Database is active.')

    def load_waypoints(self):
        if os.path.exists(self.waypoints_db_file):
            try:
                with open(self.waypoints_db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.get_logger().error(f"Error reading JSON: {e}")
        return {"home": {"x": 0.0, "y": 0.0, "yaw": 0.0}}

    def save_waypoints(self):
        try:
            with open(self.waypoints_db_file, 'w', encoding='utf-8') as f:
                json.dump(self.waypoints, f, indent=4)
        except Exception as e:
            self.get_logger().error(f"Error writing JSON: {e}")

    def sync_routine(self):
        msg = String(data=json.dumps(self.waypoints))
        self.wp_list_pub.publish(msg)
        self.publish_markers()

    def command_cb(self, msg):
        try:
            payload = json.loads(msg.data)
            action = payload.get("action")
            name = payload.get("name", "").lower().replace(" ", "_")

            if action == "save":
                self.waypoints[name] = {
                    "x": float(payload.get("x", 0.0)),
                    "y": float(payload.get("y", 0.0)),
                    "yaw": float(payload.get("yaw", 0.0))
                }
                self.save_waypoints()
                self.sync_routine() 
                self.get_logger().info(f"Waypoint '{name.upper()}' saved.")
                
            elif action == "delete":
                if name in self.waypoints:
                    del self.waypoints[name]
                    self.save_waypoints()
                    self.sync_routine()
                    self.get_logger().info(f"Waypoint '{name.upper()}' deleted.")

            elif action == "go_to_named":
                if name in self.waypoints:
                    wp = self.waypoints[name]
                    cmd = {
                        "action": "go_to",
                        "x": wp["x"],
                        "y": wp["y"],
                        "yaw": wp["yaw"]
                    }
                    self.tactical_pub.publish(String(data=json.dumps(cmd)))
                    self.get_logger().info(f"Robot is heading to waypoint '{name.upper()}'")
                else:
                    self.get_logger().warn(f"Waypoint '{name}' not found in database!")

        except Exception as e:
            self.get_logger().error(f"Error processing command: {e}")

    def publish_markers(self):
        msg = MarkerArray()
        idx = 0
        for name, wp in self.waypoints.items():
            marker = Marker()
            marker.header.frame_id = "map"
            marker.ns = "waypoints"
            marker.id = idx
            marker.type = Marker.CYLINDER
            marker.action = Marker.ADD
            marker.pose.position.x = float(wp['x'])
            marker.pose.position.y = float(wp['y'])
            marker.pose.position.z = 0.1
            marker.scale.x = 0.3
            marker.scale.y = 0.3
            marker.scale.z = 0.2
            marker.color.a = 0.7
            marker.color.r, marker.color.g, marker.color.b = 0.0, 0.7, 1.0 
            msg.markers.append(marker)
            
            text_marker = Marker()
            text_marker.header.frame_id = "map"
            text_marker.ns = "waypoints_labels"
            text_marker.id = idx + 1000
            text_marker.type = Marker.TEXT_VIEW_FACING
            text_marker.action = Marker.ADD
            text_marker.pose.position.x = float(wp['x'])
            text_marker.pose.position.y = float(wp['y'])
            text_marker.pose.position.z = 0.4
            text_marker.scale.z = 0.2
            text_marker.color.a = 1.0
            text_marker.color.r, text_marker.color.g, text_marker.color.b = 1.0, 1.0, 1.0
            text_marker.text = name.upper()
            msg.markers.append(text_marker)
            idx += 1
            
        self.marker_pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = WaypointManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()