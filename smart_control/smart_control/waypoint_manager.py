#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray
from smart_interfaces.msg import SmartCommand

import json
import os
import math

class WaypointManager(Node):
    def __init__(self):
        super().__init__('waypoint_manager')
        
        self.wp_list_pub = self.create_publisher(String, '/waypoints_list', 10)
        self.cmd_pub = self.create_publisher(SmartCommand, '/smart_command', 10)
        self.marker_pub = self.create_publisher(MarkerArray, '/smart_waypoints_markers', 10)

        self.create_subscription(SmartCommand, '/smart_command', self.command_cb, 10)
        
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
        if msg.target_system not in ('waypoints', 'nav'):
            return
        if msg.target_system == 'nav' and msg.command != 'go_to_named':
            return

        payload = {}
        if msg.payload_json:
            try:
                payload = json.loads(msg.payload_json)
            except Exception as e:
                self.get_logger().error(f"Invalid JSON in SmartCommand ({msg.target_system}:{msg.command}): {e}")
                return
            if not isinstance(payload, dict):
                self.get_logger().error(f"Expected JSON object in SmartCommand ({msg.target_system}:{msg.command}), got {type(payload).__name__}")
                return

        raw_name = payload.get("name", "")
        if not isinstance(raw_name, str):
            raw_name = str(raw_name)
        name = raw_name.strip().lower().replace(" ", "_")

        # --- PROCESSING COMMANDS FOR THE DATABASE---
        if msg.target_system == 'waypoints':
            action = msg.command
            if not name:
                self.get_logger().warn(f"Empty waypoint name for command '{action}'. Ignored.")
                return
            
            if action == "save":
                tab = str(payload.get("tab", "global"))
                
                # If an array of points arrived, save it as a route
                if "points" in payload:
                    pts = payload["points"]
                    if not isinstance(pts, list) or len(pts) == 0:
                        self.get_logger().error("Invalid or empty 'points' array for route save.")
                        return
                    clean_pts = []
                    for p in pts:
                        if not isinstance(p, (list, tuple)) or len(p) < 2:
                            self.get_logger().error(f"Invalid point in route save: {p}")
                            return
                        try:
                            px = float(p[0])
                            py = float(p[1])
                            pyaw = float(p[2]) if len(p) > 2 else 0.0
                        except (ValueError, TypeError) as e:
                            self.get_logger().error(f"Non-numeric coordinate in route save: {e}")
                            return
                        if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(pyaw)):
                            self.get_logger().error("Non-finite coordinate in route save.")
                            return
                        clean_pts.append([px, py, pyaw])
                    self.waypoints[name] = {
                        "type": "route",
                        "tab": tab,
                        "points": clean_pts
                    }
                    self.get_logger().info(f"Route '{name.upper()}' saved with {len(clean_pts)} points.")
                # Otherwise, save as a single point
                else:
                    try:
                        px = float(payload.get("x", 0.0))
                        py = float(payload.get("y", 0.0))
                        pyaw = float(payload.get("yaw", 0.0))
                    except (ValueError, TypeError) as e:
                        self.get_logger().error(f"Non-numeric coordinate in waypoint save: {e}")
                        return
                    if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(pyaw)):
                        self.get_logger().error("Non-finite coordinate in waypoint save.")
                        return
                    self.waypoints[name] = {
                        "type": "point",
                        "tab": tab,
                        "x": px,
                        "y": py,
                        "yaw": pyaw
                    }
                    self.get_logger().info(f"Waypoint '{name.upper()}' saved.")
                
                self.save_waypoints()
                self.sync_routine() 
                
            elif action == "delete":
                if name in self.waypoints:
                    del self.waypoints[name]
                    self.save_waypoints()
                    self.sync_routine()
                    self.get_logger().info(f"Item '{name.upper()}' deleted.")

        # --- SENDING COMMANDS TO THE ROBOT (NAVIGATOR) ---
        elif msg.target_system == 'nav' and msg.command == 'go_to_named':
            if name in self.waypoints:
                wp = self.waypoints[name]
                try:
                    laps = min(100, max(1, int(payload.get("laps", 1))))
                except (ValueError, TypeError):
                    self.get_logger().error(f"Invalid 'laps' value in go_to_named: {payload.get('laps')}")
                    return
                cmd_msg = SmartCommand()
                cmd_msg.target_system = 'nav'
                
                # If this is a route, send an array of points
                if wp.get("type") == "route":
                    cmd_msg.command = 'waypoints'
                    cmd_msg.payload_json = json.dumps({"points": wp["points"], "laps": laps, "name": name})
                    self.get_logger().info(f"Sending Route '{name.upper()}' (laps={laps}) to Nav Coordinator.")
                # If a single point, go_to
                else:
                    cmd_msg.command = 'go_to'
                    cmd_msg.payload_json = json.dumps({"x": wp["x"], "y": wp["y"], "yaw": wp["yaw"], "laps": laps, "name": name})
                    self.get_logger().info(f"Sending Point '{name.upper()}' (laps={laps}) to Nav Coordinator.")
                
                self.cmd_pub.publish(cmd_msg)
            else:
                self.get_logger().warn(f"Item '{name}' not found in database!")

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
            
            # If this is a route, put a marker on the first point
            if wp.get("type") == "route":
                marker.pose.position.x = float(wp['points'][0][0])
                marker.pose.position.y = float(wp['points'][0][1])
                marker.color.r, marker.color.g, marker.color.b = 0.8, 0.2, 0.8 # Purple for routes
            else:
                marker.pose.position.x = float(wp['x'])
                marker.pose.position.y = float(wp['y'])
                marker.color.r, marker.color.g, marker.color.b = 0.0, 0.7, 1.0 # Blue for points
                
            marker.pose.position.z = 0.1
            marker.scale.x = 0.3
            marker.scale.y = 0.3
            marker.scale.z = 0.2
            marker.color.a = 0.7
            msg.markers.append(marker)
            
            text_marker = Marker()
            text_marker.header.frame_id = "map"
            text_marker.ns = "waypoints_labels"
            text_marker.id = idx + 1000
            text_marker.type = Marker.TEXT_VIEW_FACING
            text_marker.action = Marker.ADD
            text_marker.pose.position.x = marker.pose.position.x
            text_marker.pose.position.y = marker.pose.position.y
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