#!/usr/bin/env python3
import os
import sys

# In Ubuntu 24.04+, Qt6 xcb platform plugin requires libxcb-cursor0.
# If not present in system LD_LIBRARY_PATH, prepend ~/.local/lib and re-exec.
_local_lib = os.path.expanduser("~/.local/lib")
if os.path.exists(_local_lib) and _local_lib not in os.environ.get("LD_LIBRARY_PATH", ""):
    _ld = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = f"{_local_lib}:{_ld}" if _ld else _local_lib
    try:
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
    except Exception:
        pass

import json
import socket
import subprocess
import threading
import time

# Load the exact same environment as an interactive terminal (~/.bashrc:
# ROS setup, RMW_IMPLEMENTATION, CYCLONEDDS_URI, etc.). Needed when started
# from a .desktop shortcut, where ~/.bashrc is not sourced.
if "CYCLONEDDS_URI" not in os.environ:
    try:
        _res = subprocess.check_output(
            ["bash", "-ic", "python3 -c 'import os, json; print(\"__ENV__\" + json.dumps(dict(os.environ)))'"],
            text=True, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        _line = [l for l in _res.splitlines() if l.startswith("__ENV__")][-1]
        os.environ.update(json.loads(_line[len("__ENV__"):]))
    except Exception:
        pass

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# ================= CONFIGURATION =================
ROBOT_USER = "oleksandr"
ROBOT_IP = "192.168.31.100"

# Paths to startup scripts
ROBOT_SSH_SCRIPT = "~/ros2_ws/src/smart_robotics/Infrastructure_as_Code\\ /autostart/start_robot.sh"
LOCAL_SERVER_SCRIPT = os.path.expanduser(
    "~/ros2_ws/src/smart_robotics/Infrastructure_as_Code /autostart/start_server.sh"
)

# Web UI URL and port (served by smart_server web_server node)
WEB_UI_URL = "http://localhost:8080"
WEB_UI_PORT = 8080

# Default world files (.sdf) — automatically augmented from smart_sim2real/worlds
WORLDS_DIR = os.path.expanduser("~/ros2_ws/src/smart_robotics/smart_sim2real/worlds")
DEFAULT_WORLDS = [
    "213.sdf",
    "kitchen.sdf",
    "shelter.sdf",
    "shelter_zero.sdf",
    "shelter_zero_empty.sdf",
    "shelter_zero_map.sdf",
]

SIM_LAUNCH_FILES = [
    "sim_master.launch.py",
    "sim_master_asym.launch.py",
    "sim_master_baseline.launch.py",
]
# =================================================


def discover_worlds():
    worlds = list(DEFAULT_WORLDS)
    if os.path.isdir(WORLDS_DIR):
        for fname in sorted(os.listdir(WORLDS_DIR)):
            if fname.endswith(".sdf") and fname not in worlds:
                worlds.append(fname)
    return worlds


class BackendSignaler(QObject):
    web_ready = pyqtSignal()
    status_update = pyqtSignal(str)


class SmartControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMART Robotics — Operator Station")
        self.resize(540, 480)
        self.active_mode = "none"
        self.topbar_manually_hidden = False

        self.signals = BackendSignaler()
        self.signals.web_ready.connect(self.switch_to_dashboard)
        self.signals.status_update.connect(self.update_status_label)

        # QStackedWidget switches between Launcher screen and embedded Web Dashboard
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.init_launcher_screen()
        self.init_dashboard_screen()

    # ---------------- SCREEN 1: Configuration & Launch ----------------
    def init_launcher_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- Tab 1: Simulation (Sim2Real) ---
        sim_tab = QWidget()
        sim_layout = QVBoxLayout(sim_tab)

        sim_params = QGroupBox("World & Sensor Configuration")
        sp_l = QVBoxLayout(sim_params)

        # Launch preset selection
        l_row = QHBoxLayout()
        l_row.addWidget(QLabel("Launch preset:"))
        self.sim_launch_preset = QComboBox()
        self.sim_launch_preset.addItems(SIM_LAUNCH_FILES)
        l_row.addWidget(self.sim_launch_preset)
        sp_l.addLayout(l_row)

        # World map selection
        w_row = QHBoxLayout()
        w_row.addWidget(QLabel("World file (world):"))
        self.sim_world = QComboBox()
        self.sim_world.addItems(discover_worlds())
        self.sim_world.setEditable(True)
        w_row.addWidget(self.sim_world)
        sp_l.addLayout(w_row)

        # Parameter checkboxes
        self.sim_gui = QCheckBox("Gazebo GUI Window (gui:=true)")
        self.sim_use_arm = QCheckBox("Enable Manipulator (use_arm:=true)")
        self.sim_3d_lidar = QCheckBox("3D LiDAR + Stabilized Frame (use_3d_lidar:=true)")
        self.sim_stab_lidar = QCheckBox("Stabilize LiDAR Frame (stabilize_lidar:=true)")
        self.sim_stab_lidar.setChecked(True)
        self.sim_stab_lidar.setEnabled(False)
        self.sim_god_mode = QCheckBox("God Mode Odometry (god_mode:=true)")

        # Couple 3D LiDAR and frame stabilization
        self.sim_3d_lidar.toggled.connect(self.sim_stab_lidar.setEnabled)

        sp_l.addWidget(self.sim_gui)
        sp_l.addWidget(self.sim_use_arm)
        sp_l.addWidget(self.sim_3d_lidar)
        sp_l.addWidget(self.sim_stab_lidar)
        sp_l.addWidget(self.sim_god_mode)
        sim_layout.addWidget(sim_params)

        btn_sim = QPushButton("Launch Simulation")
        btn_sim.setStyleSheet(
            "background-color: #1565c0; color: white; font-weight: bold; padding: 12px; font-size: 14px;"
        )
        btn_sim.clicked.connect(self.start_sim_mode)
        sim_layout.addStretch()
        sim_layout.addWidget(btn_sim)
        self.tabs.addTab(sim_tab, "Simulation (Sim2Real)")

        # --- Tab 2: Real Robot ---
        real_tab = QWidget()
        real_layout = QVBoxLayout(real_tab)

        info_box = QGroupBox("Connection Info")
        info_l = QVBoxLayout(info_box)
        info_l.addWidget(QLabel(f"Robot Host: <b>{ROBOT_USER}@{ROBOT_IP}</b> (tmux: <code>robot</code>)"))
        info_l.addWidget(QLabel("Local Server: <b>tmux: <code>smart_server</code></b>"))
        real_layout.addWidget(info_box)

        real_params = QGroupBox("Launch Parameters (Real Robot)")
        rp_l = QVBoxLayout(real_params)
        self.real_use_arm = QCheckBox("Enable Manipulator (use_arm:=true)")
        rp_l.addWidget(self.real_use_arm)
        real_layout.addWidget(real_params)

        btn_real = QPushButton("Launch Robot + Server")
        btn_real.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; padding: 12px; font-size: 14px;"
        )
        btn_real.clicked.connect(self.start_real_mode)
        real_layout.addStretch()
        real_layout.addWidget(btn_real)
        self.tabs.addTab(real_tab, "Real Robot")

        # Status bar and emergency stop button
        footer = QHBoxLayout()
        self.status_label = QLabel("Ready to launch")
        btn_kill = QPushButton("Stop All Processes")
        btn_kill.setStyleSheet("background-color: #b71c1c; color: white; padding: 6px;")
        btn_kill.clicked.connect(self.stop_all)
        footer.addWidget(self.status_label)
        footer.addStretch()
        footer.addWidget(btn_kill)
        layout.addLayout(footer)

        self.stack.addWidget(page)

    # ---------------- SCREEN 2: Embedded Web Dashboard ----------------
    def init_dashboard_screen(self):
        self.dashboard_page = QWidget()
        layout = QVBoxLayout(self.dashboard_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Compact control bar above the embedded Web UI
        self.topbar = QFrame()
        self.topbar.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
        self.topbar.setFixedHeight(34)
        tb_layout = QHBoxLayout(self.topbar)
        tb_layout.setContentsMargins(10, 2, 10, 2)

        self.active_mode_lbl = QLabel("Mode: Active")
        self.active_mode_lbl.setStyleSheet("font-size: 11px; color: #cccccc;")

        btn_terms = QPushButton("Logs")
        btn_terms.setToolTip("Open tmux terminal with logs")
        btn_terms.setStyleSheet("background-color: #333; color: white; padding: 2px 8px; font-size: 11px;")

        btn_reload = QPushButton("Reload")
        btn_reload.setToolTip("Reload Web Interface")
        btn_reload.setStyleSheet("background-color: #333; color: white; padding: 2px 8px; font-size: 11px;")

        btn_fs = QPushButton("⛶ Fullscreen (F11)")
        btn_fs.setToolTip("Toggle Fullscreen Mode (F11 / Esc)")
        btn_fs.setStyleSheet("background-color: #333; color: white; padding: 2px 8px; font-size: 11px;")

        btn_hide = QPushButton("▲ Hide Bar (F10)")
        btn_hide.setToolTip("Hide this bar to maximize screen space (F10)")
        btn_hide.setStyleSheet("background-color: #2b3a4a; color: #64b5f6; padding: 2px 8px; font-size: 11px;")

        btn_back = QPushButton("Stop & Return")
        btn_back.setToolTip("Stop all processes and return to launch menu")
        btn_back.setStyleSheet(
            "background-color: #c62828; color: white; font-weight: bold; padding: 2px 10px; font-size: 11px;"
        )

        btn_reload.clicked.connect(lambda: self.webview.reload())
        btn_terms.clicked.connect(self.open_tmux_logs)
        btn_fs.clicked.connect(self.toggle_fullscreen)
        btn_hide.clicked.connect(self.toggle_topbar)
        btn_back.clicked.connect(self.stop_and_return)

        tb_layout.addWidget(btn_hide)
        tb_layout.addWidget(self.active_mode_lbl)
        tb_layout.addStretch()
        tb_layout.addWidget(btn_terms)
        tb_layout.addWidget(btn_reload)
        tb_layout.addWidget(btn_fs)
        tb_layout.addWidget(btn_back)

        self.webview = QWebEngineView()
        ws = self.webview.settings()
        ws.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.webview.page().fullScreenRequested.connect(self.handle_fullscreen_requested)

        layout.addWidget(self.topbar)
        layout.addWidget(self.webview)

        # Floating pill button when topbar is hidden
        self.floating_toggle_btn = QPushButton("▼ Bar (F10)", self.dashboard_page)
        self.floating_toggle_btn.setToolTip("Show control bar (or press F10 / F11)")
        self.floating_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 30, 30, 0.85);
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(60, 60, 60, 0.95);
                border-color: #00d2ff;
            }
        """)
        self.floating_toggle_btn.clicked.connect(self.toggle_topbar)
        self.floating_toggle_btn.hide()

        self.stack.addWidget(self.dashboard_page)

    def toggle_topbar(self):
        if self.topbar.isVisible():
            self.topbar.hide()
            self.topbar_manually_hidden = True
            self.floating_toggle_btn.show()
            self.update_floating_button_pos()
        else:
            self.topbar.show()
            self.topbar_manually_hidden = False
            self.floating_toggle_btn.hide()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
            if not self.topbar_manually_hidden:
                self.topbar.show()
                self.floating_toggle_btn.hide()
            else:
                self.floating_toggle_btn.show()
                self.update_floating_button_pos()
        else:
            self.showFullScreen()
            self.topbar.hide()
            self.floating_toggle_btn.show()
            self.update_floating_button_pos()

    def handle_fullscreen_requested(self, request):
        request.accept()
        if request.toggleOn():
            self.showFullScreen()
            self.topbar.hide()
            self.floating_toggle_btn.show()
            self.update_floating_button_pos()
        else:
            self.showMaximized()
            if not self.topbar_manually_hidden:
                self.topbar.show()
                self.floating_toggle_btn.hide()
            else:
                self.floating_toggle_btn.show()
                self.update_floating_button_pos()

    def update_floating_button_pos(self):
        if hasattr(self, "floating_toggle_btn") and hasattr(self, "dashboard_page"):
            self.floating_toggle_btn.move(10, 8)
            self.floating_toggle_btn.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_floating_button_pos()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_F10:
            self.toggle_topbar()
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    # ---------------- LAUNCH LOGIC ----------------
    def update_status_label(self, text):
        self.status_label.setText(text)

    def start_real_mode(self):
        self.active_mode = "real"
        use_arm = "true" if self.real_use_arm.isChecked() else "false"
        self.active_mode_lbl.setText(f"REAL ROBOT ({ROBOT_IP}) | use_arm:={use_arm}")
        self.status_label.setText("Starting tmux session on robot via SSH...")

        def runner():
            # 1. Start robot script on the robot in background tmux
            ssh_cmd = (
                f"ssh -o ConnectTimeout=5 {ROBOT_USER}@{ROBOT_IP} "
                f"\"bash -l -c '{ROBOT_SSH_SCRIPT} {use_arm} || ~/start_robot.sh {use_arm} || ~/robot.sh {use_arm}'\""
            )
            subprocess.run(ssh_cmd, shell=True)

            self.signals.status_update.emit("Starting local smart_server...")
            # 2. Start local server script
            local_cmd = f"bash -l -c '\"{LOCAL_SERVER_SCRIPT}\" {use_arm}'"
            subprocess.run(local_cmd, shell=True)

            self.signals.status_update.emit("Waiting for Web UI server port...")
            self._wait_for_web_port()

        threading.Thread(target=runner, daemon=True).start()

    def start_sim_mode(self):
        self.active_mode = "sim"
        launch_file = self.sim_launch_preset.currentText().strip()
        world = self.sim_world.currentText().strip()
        gui = "true" if self.sim_gui.isChecked() else "false"
        use_arm = "true" if self.sim_use_arm.isChecked() else "false"
        use_3d = "true" if self.sim_3d_lidar.isChecked() else "false"
        stab = "true" if self.sim_stab_lidar.isChecked() else "false"
        god = "true" if self.sim_god_mode.isChecked() else "false"

        self.active_mode_lbl.setText(
            f"SIMULATION ({launch_file}) | World: {world} | 3D LiDAR: {use_3d} | Arm: {use_arm}"
        )
        self.status_label.setText("Starting tmux session 'sim_session'...")

        launch_cmd = (
            f"ros2 launch smart_master {launch_file} "
            f"world:={world} gui:={gui} use_arm:={use_arm} "
            f"use_3d_lidar:={use_3d} stabilize_lidar:={stab} god_mode:={god}"
        )

        def runner():
            # Clean up any leftover simulation session and launch a fresh tmux session
            tmux_sim = (
                "tmux kill-session -t sim_session 2>/dev/null; "
                "tmux kill-session -t arm_session 2>/dev/null; "
                "tmux kill-session -t mission_nav_session 2>/dev/null; "
                "tmux kill-session -t radiation_session 2>/dev/null; "
                "tmux new-session -d -s sim_session; "
                "tmux send-keys -t sim_session 'source /opt/ros/jazzy/setup.bash && source ~/ros2_ws/install/setup.bash' C-m; "
                "tmux send-keys -t sim_session 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' C-m; "
                f"tmux send-keys -t sim_session '{launch_cmd}' C-m"
            )
            subprocess.run(tmux_sim, shell=True)
            self.signals.status_update.emit("Waiting for Web UI server initialization...")
            self._wait_for_web_port()

        threading.Thread(target=runner, daemon=True).start()

    def _wait_for_web_port(self):
        # Wait up to 25 seconds for the Web UI port to accept connections
        for _ in range(25):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                if s.connect_ex(("127.0.0.1", WEB_UI_PORT)) == 0:
                    time.sleep(1.0)
                    break
            time.sleep(1.0)
        self.signals.web_ready.emit()

    def switch_to_dashboard(self):
        self.webview.setUrl(QUrl(WEB_UI_URL))
        self.stack.setCurrentIndex(1)
        self.showMaximized()
        self.update_floating_button_pos()

    def open_tmux_logs(self):
        # Open terminal attached to the active tmux session
        cmd = (
            'gnome-terminal -- bash -c "'
            "tmux attach -t sim_session 2>/dev/null || "
            "tmux attach -t smart_server 2>/dev/null || "
            f"ssh -t {ROBOT_USER}@{ROBOT_IP} 'tmux attach -t robot'; exec bash\""
        )
        subprocess.Popen(cmd, shell=True)

    def stop_all(self):
        self.status_label.setText("Stopping all sessions...")
        # Stop local tmux sessions and Gazebo/ROS processes
        subprocess.Popen(
            "tmux kill-session -t smart_server 2>/dev/null; "
            "tmux kill-session -t sim_session 2>/dev/null; "
            "tmux kill-session -t arm_session 2>/dev/null; "
            "tmux kill-session -t mission_nav_session 2>/dev/null; "
            "tmux kill-session -t radiation_session 2>/dev/null; "
            "tmux kill-session -t yolo_session 2>/dev/null; "
            "killall -9 gz ruby rviz2 zenoh-bridge-dds 2>/dev/null",
            shell=True,
        )
        # Stop remote tmux session on robot if in real mode
        if self.active_mode == "real":
            subprocess.Popen(
                f"ssh -o ConnectTimeout=2 -o BatchMode=yes {ROBOT_USER}@{ROBOT_IP} "
                "'tmux kill-session -t robot 2>/dev/null; killall -9 zenoh-bridge-dds 2>/dev/null'",
                shell=True,
            )
        self.active_mode = "none"
        self.status_label.setText("All processes stopped")

    def stop_and_return(self):
        self.stop_all()
        if self.isFullScreen():
            self.showNormal()
        self.showNormal()
        self.resize(540, 480)
        self.topbar.show()
        self.topbar_manually_hidden = False
        if hasattr(self, "floating_toggle_btn"):
            self.floating_toggle_btn.hide()
        self.stack.setCurrentIndex(0)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SmartControlApp()
    win.show()
    sys.exit(app.exec())
