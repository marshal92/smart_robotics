#!/usr/bin/env python3

import gzip
import http.server
import os
import socket
import socketserver
import threading
import urllib.parse
from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node


class _ThreadingWebServer(socketserver.ThreadingTCPServer):
    """Concurrent TCP HTTP server that never stalls on idle client sockets."""

    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128


class MultiDirectoryRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler serving web_ui_2.0 dist, ROS package meshes, and workspace installs."""

    ws_root = ""
    dist_dir = ""
    _pkg_cache = {}
    _gzip_cache = {}
    _gzip_lock = threading.Lock()
    _GZIP_EXTS = (".js", ".css", ".html", ".svg", ".json", ".stl")
    _ASSET_CACHE_EXTS = (".js", ".css", ".stl", ".dae", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".woff2")
    _MAX_GZIP_BYTES = 5 * 1024 * 1024

    def setup(self):
        # Bound socket reads so idle browser preconnect sockets cannot hang handler threads forever
        self.request.settimeout(15.0)
        super().setup()

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, socket.timeout, OSError):
            pass

    def finish(self):
        try:
            super().finish()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, socket.timeout, OSError):
            pass

    def _clean_url_path(self):
        return urllib.parse.unquote(urllib.parse.urlparse(self.path).path)

    def translate_path(self, path):
        """Map the URL path to the correct local directory."""
        parsed_path = urllib.parse.urlparse(path)
        clean_path = urllib.parse.unquote(parsed_path.path)

        if clean_path.startswith('/install') or clean_path.startswith('/src'):
            requested_path = os.path.abspath(os.path.join(self.ws_root, clean_path.lstrip('/')))
            if os.path.commonpath([os.path.abspath(self.ws_root), requested_path]) != os.path.abspath(self.ws_root):
                return "/__denied__"
            return requested_path

        if clean_path.startswith('/packages/'):
            parts = clean_path.lstrip('/').split('/')
            if len(parts) >= 2:
                pkg_name = parts[1]
                allowed_pkgs = (
                    'ugv_tracked_description',
                    'manipulator_description',
                    'smart_master',
                    'smart_server',
                    'smart_sim2real',
                    'smart_moveit_config',
                )
                if pkg_name in allowed_pkgs:
                    try:
                        if pkg_name not in self._pkg_cache:
                            self._pkg_cache[pkg_name] = os.path.abspath(get_package_share_directory(pkg_name))
                        pkg_share = self._pkg_cache[pkg_name]
                        remainder = os.path.join(*parts[2:]) if len(parts) > 2 else ''
                        requested_path = os.path.abspath(os.path.join(pkg_share, remainder))
                        if os.path.commonpath([pkg_share, requested_path]) != pkg_share:
                            return "/__denied__"
                        return requested_path
                    except Exception:
                        pass
            return "/__denied__"

        local_path = os.path.abspath(os.path.join(self.dist_dir, clean_path.lstrip('/')))
        dist_abs = os.path.abspath(self.dist_dir)
        if os.path.commonpath([dist_abs, local_path]) != dist_abs:
            return "/__denied__"
        if clean_path == '/' or (not os.path.exists(local_path) and '.' not in os.path.basename(clean_path)):
            return os.path.join(self.dist_dir, 'index.html')
        return local_path

    def do_GET(self):
        accept_enc = self.headers.get('Accept-Encoding', '').lower()
        if 'gzip' in accept_enc and 'Range' not in self.headers:
            fs_path = self.translate_path(self.path)
            if os.path.isdir(fs_path):
                candidate = os.path.join(fs_path, 'index.html')
                if os.path.isfile(candidate):
                    fs_path = candidate

            if os.path.isfile(fs_path) and fs_path.lower().endswith(self._GZIP_EXTS):
                try:
                    st = os.stat(fs_path)
                    if st.st_size <= self._MAX_GZIP_BYTES:
                        compressed = self._get_or_compress(fs_path, st)
                        self.send_response(200)
                        self.send_header('Content-type', self.guess_type(fs_path))
                        self.send_header('Content-Encoding', 'gzip')
                        self.send_header('Vary', 'Accept-Encoding')
                        self.send_header('Content-Length', str(len(compressed)))
                        self.send_header('Last-Modified', self.date_time_string(st.st_mtime))
                        self.end_headers()
                        self.wfile.write(compressed)
                        return
                except OSError:
                    pass

        super().do_GET()

    @classmethod
    def _get_or_compress(cls, fs_path, st):
        key = (fs_path, st.st_mtime_ns, st.st_size)
        with cls._gzip_lock:
            cached = cls._gzip_cache.get(key)
        if cached is not None:
            return cached

        with open(fs_path, 'rb') as f:
            compressed = gzip.compress(f.read(), compresslevel=5)

        with cls._gzip_lock:
            if len(cls._gzip_cache) >= 64:
                cls._gzip_cache.clear()
            cls._gzip_cache[key] = compressed
        return compressed

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        clean_path = self._clean_url_path().lower()
        if clean_path.startswith('/assets/'):
            self.send_header('Cache-Control', 'public, max-age=86400, immutable')
        elif clean_path.endswith(self._ASSET_CACHE_EXTS) and not clean_path.endswith('.html'):
            self.send_header('Cache-Control', 'public, max-age=3600')
        else:
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        return super().end_headers()


class WebServerNode(Node):
    def __init__(self):
        super().__init__('web_server')
        self.declare_parameter('port', 8080)
        self.port = self.get_parameter('port').value

        share_dir = get_package_share_directory('smart_server')
        self.ws_root = os.path.abspath(os.path.join(share_dir, '..', '..', '..', '..'))
        self.dist_dir = os.path.join(self.ws_root, 'src', 'smart_robotics', 'Infrastructure_as_Code', 'web_ui_2.0', 'dist')

        self.get_logger().info(f"Workspace root: {self.ws_root}")
        self.get_logger().info(f"Web UI dist folder: {self.dist_dir}")

        if not os.path.exists(self.dist_dir):
            self.get_logger().warn(f"Dist folder does not exist! Did you run 'npm run build'? Path: {self.dist_dir}")

        MultiDirectoryRequestHandler.ws_root = self.ws_root
        MultiDirectoryRequestHandler.dist_dir = self.dist_dir

        self.server_thread = threading.Thread(target=self.serve, daemon=True)
        self.server_thread.start()

    def serve(self):
        httpd = _ThreadingWebServer(("", self.port), MultiDirectoryRequestHandler)
        self.get_logger().info(f"Started multi-threaded Web UI server on port {self.port}")
        httpd.serve_forever()


def main(args=None):
    rclpy.init(args=args)
    node = WebServerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
