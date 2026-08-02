#!/usr/bin/env python3

import os
import sys
import threading
import http.server
import socketserver
import urllib.parse
from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node

class MultiDirectoryRequestHandler(http.server.SimpleHTTPRequestHandler):
    # This will be set by the node before serving
    ws_root = ""
    dist_dir = ""

    def translate_path(self, path):
        """Map the URL path to the correct local directory."""
        # Clean up path
        parsed_path = urllib.parse.urlparse(path)
        clean_path = parsed_path.path
        
        # Resolve aliases
        if clean_path.startswith('/install') or clean_path.startswith('/src'):
            # Serve from workspace root
            return os.path.join(self.ws_root, clean_path.lstrip('/'))
        else:
            # Serve everything else from the Vue 'dist' folder
            local_path = os.path.join(self.dist_dir, clean_path.lstrip('/'))
            # Vue Router support: if path doesn't exist and doesn't have an extension, return index.html
            if not os.path.exists(local_path) and '.' not in os.path.basename(clean_path):
                return os.path.join(self.dist_dir, 'index.html')
            return local_path

    def end_headers(self):
        # Allow CORS for everything just in case
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        return super(MultiDirectoryRequestHandler, self).end_headers()

class WebServerNode(Node):
    def __init__(self):
        super().__init__('web_server')
        self.declare_parameter('port', 8080)
        self.port = self.get_parameter('port').value

        # Calculate paths
        # get_package_share_directory gives something like: ~/ros2_ws/install/smart_server/share/smart_server
        share_dir = get_package_share_directory('smart_server')
        self.ws_root = os.path.abspath(os.path.join(share_dir, '..', '..', '..', '..'))
        
        # Note the space in Infrastructure_as_Code 
        self.dist_dir = os.path.join(self.ws_root, 'src', 'smart_robotics', 'Infrastructure_as_Code ', 'web_ui', 'dist')
        
        self.get_logger().info(f"Workspace root: {self.ws_root}")
        self.get_logger().info(f"Web UI dist folder: {self.dist_dir}")

        if not os.path.exists(self.dist_dir):
            self.get_logger().warn(f"Dist folder does not exist! Did you run 'npm run build'? Path: {self.dist_dir}")

        # Configure RequestHandler
        MultiDirectoryRequestHandler.ws_root = self.ws_root
        MultiDirectoryRequestHandler.dist_dir = self.dist_dir

        # Start server in a background thread
        self.server_thread = threading.Thread(target=self.serve)
        self.server_thread.daemon = True
        self.server_thread.start()

    def serve(self):
        socketserver.TCPServer.allow_reuse_address = True
        httpd = socketserver.TCPServer(("", self.port), MultiDirectoryRequestHandler)
        self.get_logger().info(f"Started Web UI server on port {self.port}")
        httpd.serve_forever()

def main(args=None):
    rclpy.init(args=args)
    node = WebServerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
