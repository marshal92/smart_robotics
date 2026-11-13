# Smart Robotics (ROS 2 Jazzy)

Supervisory control architecture for autonomous mobile robots and 6-DOF manipulators built on **ROS 2 Jazzy**, designed for radiation-hazardous environments and degraded/intermittent communications.

The system integrates **Nav2 (MPPI + Lifelong SLAM)**, the **ALARA** radiation-aware navigation stack (`smart_radiation` + C++ `smart_radiation_plugins`), a unified `/smart_command` fault-tolerant command bus, **Gazebo Sim (`smart_sim2real`)**, and the **Web UI 2.0** 3D Digital Twin interface (`Vue 3 + Vite + Three.js`).

---

## Table of Contents

1. [Three-Tier Architecture (Edge / Fog / Cloud)](#1-three-tier-architecture-edge--fog--cloud)
2. [Repository Layout and ROS 2 Packages](#2-repository-layout-and-ros-2-packages)
3. [Communications and Routing (CycloneDDS + Zenoh Bridge)](#3-communications-and-routing-cyclonedds--zenoh-bridge)
4. [Build and Quick Start](#4-build-and-quick-start)
5. [Control Architecture, Navigation, and Shadow Mode](#5-control-architecture-navigation-and-shadow-mode)
6. [ALARA Radiation Subsystem](#6-alara-radiation-subsystem)
7. [Manipulator Control (MoveIt 2 / Servo / 2.5D Manual)](#7-manipulator-control-moveit-2--servo--25d-manual)
8. [Web UI 2.0 and 3D Digital Twin](#8-web-ui-20-and-3d-digital-twin)
9. [Unified Command Bus (`/smart_command`) and Telemetry (`/smart_telemetry`)](#9-unified-command-bus-smart_command-and-telemetry-smart_telemetry)

---

## 1. Three-Tier Architecture (Edge / Fog / Cloud)

```text
  [Edge: ESP32-S3] <──USB Serial──▶ [micro_ros_agent]
                                           │
                                    [Fog: Onboard Robot]
                        (CycloneDDS: control_core, Nav2, SLAM,
                         telemetry_mux, trajectory_bridge, radiation)
                                           │
                          Zenoh Bridge (TCP :7447, Allowlist)
                                           │
                                  [Cloud: Operator Station]
                    ┌──────────────────────┴──────────────────────┐
                    ▼                                             ▼
      rosbridge_websocket (:9090)                    HTTP web_server (:8080)
                    └──────────────▶ Web UI 2.0 (Vue 3 + Three.js)
                     + On-demand: MoveIt 2, MoveIt Servo, Shadow Mode, AI
```

1. **Edge (MCU Peripheral / ESP32-S3):** Runs **micro-ROS** (`micro_ros_agent serial --dev /dev/esp32s3`), handling low-level chassis and manipulator actuation (`/arm/servo_cmd`, `/arm/joint_states_raw`).
2. **Fog (Onboard Robot Computer):** Isolated CycloneDDS domain (`rmw_cyclonedds_cpp`) running autonomy- and safety-critical nodes: hardware drivers, `smart_control` + C++ `smart_plugins`, Nav2 / SLAM Toolbox, and the ALARA radiation subsystem (`smart_radiation` / `smart_radiation_plugins`).
3. **Cloud (Operator Workstation / Server):** Supervision and heavy compute: `rosbridge_websocket`, multi-threaded HTTP server `web_server`, map image encoding (`map_to_image`), 3D environment visualization (`sdf_visualizer`), Shadow Mode (`shadow_teleop_real` / `shadow_teleop_sim`), manipulator orchestrator `twin_orchestrator` (launches MoveIt 2 / Servo on demand), and the optional AI stack (`smart_ai`).

---

## 2. Repository Layout and ROS 2 Packages

| Package / Directory | Type | Purpose |
|---|---|---|
| [`smart_interfaces`](smart_interfaces/CMakeLists.txt) | `ament_cmake` (`rosidl`) | Custom messages [`SmartCommand.msg`](smart_interfaces/msg/SmartCommand.msg) and [`SmartTelemetry.msg`](smart_interfaces/msg/SmartTelemetry.msg) |
| [`smart_master`](smart_master/CMakeLists.txt) | `ament_cmake` | Top-level URDF assembly [`full_system.urdf.xacro`](smart_master/urdf/full_system.urdf.xacro) and master launches [`sim_master.launch.py`](smart_master/launch/sim_master.launch.py), [`real_master.launch.py`](smart_master/launch/real_master.launch.py) |
| [`smart_control`](smart_control/setup.py) | `ament_python` | Mission lifecycle, waypoint storage, safety watchdog, relocalization, and tactical maneuvers ([`control_core.launch.py`](smart_control/launch/control_core.launch.py)) |
| [`smart_plugins`](smart_plugins/CMakeLists.txt) | `ament_cmake` (C++) | Real-time C++ core nodes: `nav_coordinator`, `telemetry_mux`, `trajectory_bridge`, `stabilized_frame_publisher_node` |
| [`smart_nav`](smart_nav/CMakeLists.txt) | `ament_cmake` | Nav2 (MPPI + `RadiationLayer`) and SLAM Toolbox configs ([`nav2_params.yaml`](smart_nav/config/nav2_params.yaml)), mapping/lifelong launches, and `maps/` |
| [`smart_radiation`](smart_radiation/setup.py) | `ament_python` | Radiation lifecycle (`radiation_manager`), sigmoid field server (`radiation_field_server`), AccuRad serial driver (`accurad_serial_node`), map generators/viewers, and experiment logger |
| [`smart_radiation_plugins`](smart_radiation_plugins/CMakeLists.txt) | `ament_cmake` (C++) | Nav2 costmap plugin `smart_radiation_plugins::RadiationLayer` plus C++ nodes `radiation_mapper_node`, `virtual_geiger_node`, `alara_speed_reflex_node` |
| [`smart_server`](smart_server/setup.py) | `ament_python` | Cloud infrastructure: `web_server`, `rosbridge_websocket`, `twin_orchestrator`, `map_to_image`, `shadow_teleop_*`, `sdf_visualizer`, `heartbeat_pub`; on-demand manipulator launches |
| [`smart_sim2real`](smart_sim2real/CMakeLists.txt) | `ament_cmake` | Gazebo Sim setup ([`sim.launch.py`](smart_sim2real/launch/sim.launch.py)), [`sim_wrapper.urdf.xacro`](smart_sim2real/urdf/sim_wrapper.urdf.xacro), `ros_gz_bridge`, EKF (`robot_localization`), and SDF worlds |
| [`smart_moveit_config`](smart_moveit_config/package.xml) | `ament_cmake` | MoveIt 2 and MoveIt Servo configuration (`SRDF`, kinematics, controllers, `servo_config.yaml`) used by `arm_moveit.launch.py` and `arm_servo.launch.py` |
| [`smart_ai`](smart_ai/setup.py) | `ament_python` | Voice control (`voice_listener_node` / Faster-Whisper), LLM/RegEx dispatcher (`semantic_dispatcher_node`), YOLO detection (`yolo_publisher`), and Visual Servoing (`spatial_projector_node`) |
| [`smart_sandbox`](smart_sandbox/setup.py) | `ament_python` | Experimental evaluation loggers and MPPI / trajectory analysis scripts |
| [`Infrastructure_as_Code`](Infrastructure_as_Code/COLCON_IGNORE) | Non-ROS dir (`COLCON_IGNORE`) | PyQt6 launcher `smart_launcher.py`, tmux autostart scripts, CycloneDDS configs, 4WD Xacro configs, and [`web_ui_2.0`](Infrastructure_as_Code/web_ui_2.0/README.md) frontend |

---

## 3. Communications and Routing (CycloneDDS + Zenoh Bridge)

Communication between the onboard computer (**Fog**) and the operator station (**Cloud**) uses a **Zenoh Bridge (`zenoh-bridge-dds`)** TCP tunnel on port `7447` with multicast disabled (`--no-multicast-scouting`) and explicit topic allowlisting in [`start_robot.sh`](Infrastructure_as_Code/autostart/start_robot.sh) and [`start_server.sh`](Infrastructure_as_Code/autostart/start_server.sh):

* **Control & Commands:** `/cmd_vel`, `/cmd_light`, `/smart_command`, `/initialpose`, `/goal_pose`, `/clicked_point`
* **Telemetry & Status:** `/smart_telemetry`, `/operator_heartbeat`, `/waypoints_list`, `/smart_waypoints_markers`, `/radiation/status`, `/rosout`
* **Mapping & TF:** `/tf`, `/tf_static`, `/robot_description`, `/map`, `/map_updates`, `/radiation_map`, `/radiation_image/compressed`, `/plan`
* **Camera & Manipulator:** `/camera/image_raw/compressed`, `/arm_joint_states`, `/arm_controller/joint_trajectory`, plus action topics under `arm_controller/follow_joint_trajectory`

When operating with the real robot (`use_sim_time:=false`), [`server.launch.py`](smart_server/launch/server.launch.py) spawns local `robot_state_publisher` (remapping `/tf` -> `/tf_server_local`) and `joint_state_publisher` (`source_list: ['/arm_joint_states']`) instances on the server so Web UI 2.0 and MoveIt obtain URDF descriptions locally without flooding the Zenoh link.

---

## 4. Build and Quick Start

### Build ROS 2 Workspace and Web UI Frontend

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source ~/ros2_ws/install/setup.bash

# Build Web UI 2.0 production bundle (dist/ served by smart_server/web_server.py)
bash ~/ros2_ws/src/smart_robotics/Infrastructure_as_Code/web_ui_2.0/build_ui.sh
```

### Graphical Operator Launcher (Recommended)

```bash
python3 ~/ros2_ws/src/smart_robotics/Infrastructure_as_Code/autostart/smart_launcher.py
```

[`smart_launcher.py`](Infrastructure_as_Code/autostart/smart_launcher.py) (PyQt6 + `QWebEngineView`) provides two operational tabs:
* **Simulation (Sim2Real):** launches `sim_master.launch.py` inside the `sim_session` tmux session with selectable worlds (`worlds/*.sdf`), Gazebo GUI toggle, manipulator (`use_arm`), 3D LiDAR (`use_3d_lidar` + `stabilize_lidar`), and `god_mode`.
* **Real Robot:** launches `start_robot.sh` (`robot` tmux session) on the robot over SSH and `start_server.sh` (`smart_server` tmux session) locally.

### Manual CLI Launch

**Simulation (Full Stack):**
```bash
ros2 launch smart_master sim_master.launch.py \
  world:=213.sdf gui:=false use_arm:=true use_3d_lidar:=false god_mode:=false
```

**Real Robot and Operator Server:**
```bash
# On the robot onboard computer:
bash ~/ros2_ws/src/smart_robotics/Infrastructure_as_Code/autostart/start_robot.sh true

# On the operator station (IP_ROBOTA is configured in start_server.sh):
bash ~/ros2_ws/src/smart_robotics/Infrastructure_as_Code/autostart/start_server.sh true
```

**Web Interface & Rosbridge Endpoints:**
* HTTP (Web UI 2.0): `http://<server-ip>:8080`
* WebSocket (`rosbridge_websocket`): `ws://<server-ip>:9090`

---

## 5. Control Architecture, Navigation, and Shadow Mode

### Control Nodes (`smart_control` + `smart_plugins`)

Launched via [`control_core.launch.py`](smart_control/launch/control_core.launch.py):

* **`nav_coordinator` (C++, `smart_plugins`):** Native asynchronous `rclcpp_action::Client` interface to Nav2 (`NavigateToPose` and `NavigateThroughPoses`). Implements waypoint **Sliding Window** progression (up to 5 points), task queuing, multi-lap patrolling (`laps` up to 100), route snapshot saving for `cancel` / `resume`, and safety FSM enforcement (`rth` is permitted in any state).
* **`mission_manager`:** Manages lifecycle of the navigation stack (`tmux` session `mission_nav_session` -> `bringup_lifelong.launch.py` / `bringup_mapping.launch.py`) and radiation subsystem (`tmux` session `radiation_session` -> `radiation_bringup.launch.py`). Also handles map saving (`/slam_toolbox/serialize_map` + `map_saver_cli`), costmap clearing, SLAM pause toggling, and `FollowPath.vx_max` updates via `set_speed:<m/s>`.
* **`waypoint_manager`:** Stores named points and routes, publishes `/waypoints_list` (JSON) and `/smart_waypoints_markers` (`MarkerArray`), and expands `nav:go_to_named` into `go_to` or `waypoints`.
* **`safety_watchdog`:** Monitors `/operator_heartbeat` and `/payload/status`. When `watchdog_on` is active and comms drop, transitions `/fsm_status`: `NORMAL` -> `WARNING` (5 s) -> `EVACUATING` (25 s, automatic `nav:rth` dispatch) -> `SAFE_HOLD` (unlocked via `operator:RESUME`).
* **`tactical_executor`:** Executes relative motion commands (`move_relative`, `turn_relative`, `track_target`) with `/scan` obstacle checking and immediate preemption on `system:stop` / `nav:cancel` / `nav:rth`.
* **`recovery_relocalizer`:** Grid scan matcher over `/scan` + SLAM Toolbox posegraph reload and `/initialpose` publication on `nav:recover_localization`.
* **`telemetry_mux` (C++, `smart_plugins`):** Aggregates `/fsm_status`, `/nav_status`, `/odom`, `/radiation/dose`, `/cmd_light`, and `/payload/status` at `5 Hz` into `/smart_telemetry`.
* **`payload_manager`:** Controls payload tools (`mock_sample` -> `lfcm_drill`), headlight relay (`/cmd_light`), and publishes `/payload/status`.

### Navigation (`smart_nav`)

* Local controller: `nav2_mppi_controller::MPPIController` ([`nav2_params.yaml`](smart_nav/config/nav2_params.yaml)).
* Global planner costmap combines `static_layer`, `obstacle_layer`, `inflation_layer`, and the custom `radiation_layer` (`smart_radiation_plugins::RadiationLayer`).
* Two SLAM Toolbox operating modes:
  * **Mapping:** [`bringup_mapping.launch.py`](smart_nav/launch/bringup_mapping.launch.py) (`slam_mapping.launch.py` + Nav2).
  * **Lifelong Localization:** [`bringup_lifelong.launch.py`](smart_nav/launch/bringup_lifelong.launch.py) (`slam_lifelong.launch.py` + Nav2 using a preloaded `.posegraph` from [`smart_nav/maps`](smart_nav/maps)).

### Shadow Mode (`smart_server`)

`shadow_teleop_real` / `shadow_teleop_sim` (selected automatically by `server.launch.py` via `use_sim_time`) let the operator teleoperate a virtual "shadow" twin on the server (`/cmd_vel_shadow`) with costmap collision checking, record a validated waypoint trail, and dispatch it to `nav_coordinator` as a single `waypoints` command via `operator:execute`.

---

## 6. ALARA Radiation Subsystem

The radiation stack runs on demand (`system:rad_start` / `system:rad_on` in `mission_manager`, or manually via `ros2 launch smart_radiation radiation_bringup.launch.py`) so normal missions incur zero radiation overhead.

1. **Field Mapping (`radiation_mapper_node`, C++):** Reads `/radiation/dose` and TF (`map` -> `base_footprint`), updates the 2D `.npy` dose and weight grids (with autosave and `/dev/shm/live_rad_map.npy` for live visualization). Controlled via `is_recording` and services `/radiation_mapper/save_map`, `/radiation_mapper/clear_map`.
2. **Simulated Dosimeter (`virtual_geiger_node`, C++, node `/virtual_geiger`):** Emulates a Geiger counter over a ground-truth `.npy` map in simulation. Toggled independently (`rad_geiger_on` / `rad_geiger_off`) and automatically mutes if >1 publisher is active on `/radiation/dose` (e.g., when a physical sensor connects).
3. **Physical Dosimeter (`accurad_serial_node`):** Reads Mirion AccuRad PRD telemetry over USB serial (`/dev/accurad`, configurable scaling/parameters) and publishes dose rate to `/radiation/dose`.
4. **Field Server (`radiation_field_server`):** Applies sigmoid penalty mapping using dynamic parameters from [`radiation_params.yaml`](smart_radiation/config/radiation_params.yaml) (`d_noise`, `d_crit`, `k`) to output `/radiation_map` (`OccupancyGrid`) and `/radiation_image/compressed` for Web UI 2.0.
5. **Nav2 Costmap Layer (`smart_radiation_plugins::RadiationLayer`):** Merges `/radiation_map` into the global costmap via `std::max()`, capped by `max_cost` (`220`) so hazardous zones are avoided when safe detours exist without becoming unrecoverable hard walls.
6. **Speed Reflex (`alara_speed_reflex_node`, C++):** Dynamically publishes `/speed_limit`: limits travel speed in clean areas (`normal_speed_pct: 35%`) and boosts to `boost_speed_pct: 100%` above local dose threshold (`rad_threshold: 30%`) to minimize integrated exposure time.
7. **Orchestration (`radiation_manager`):** Single handler for `rad_*` commands coordinating parameters and services across mapper, field server, and virtual geiger while publishing state on `/radiation/status`. When disabled (`is_active:=false`, `is_recording:=false`), worker nodes remain idle with minimal CPU usage.

---

## 7. Manipulator Control (MoveIt 2 / Servo / 2.5D Manual)

Control of the 6-DOF manipulator (`arm_joint_0..arm_joint_5`, gripper `arm_clamp`) is split between the onboard/sim layer and the operator station:

* **Hardware / Sim Layer:**
  * In simulation (`sim.launch.py` with `use_arm:=true`), spawns `arm_controller` and `joint_state_broadcaster`.
  * On the real robot (`real_master.launch.py` with `use_arm:=true`), C++ node `trajectory_bridge` (`smart_plugins`) accepts both direct `trajectory_msgs/JointTrajectory` messages (`/arm_controller/joint_trajectory`) and MoveIt action goals (`arm_controller/follow_joint_trajectory`), translating them to `/arm/servo_cmd` for the ESP32.
* **Server Manipulator Backend (On Demand via `twin_orchestrator`):**
  * `system:arm_moveit_on` / `arm_moveit_off` -> [`arm_moveit.launch.py`](smart_server/launch/arm_moveit.launch.py) (`move_group`, `tactical_server`, `control_hub` in `arm_moveit_session`).
  * `system:arm_servo_on` / `arm_servo_off` -> [`arm_servo.launch.py`](smart_server/launch/arm_servo.launch.py) (`moveit_servo` with `is_primary_planning_scene_monitor=true` + `teleop_manager` in `arm_servo_session`).
  * `system:arm_off` -> stops both manipulator backends.
* **Four Modes in Web UI 2.0 (`ArmControl.vue`):**
  1. **JOINTS:** direct joint sliders `J0..J5` + clamp, `Fold`/`Unfold` presets, `LIVE FK` 3D trail, and trajectory sequencer to `/arm_controller/joint_trajectory`.
  2. **MANUAL:** browser-side cylindrical **2.5D control** (zero server MoveIt nodes needed) — damped least-squares 2D Jacobian over radius $R$ and height $Z$ on $J1/J2$, automatic wrist leveling on $J4$, roll compensation on $J5$, and local FK.
  3. **AUTO:** `Control Hub` missions, CSV sequence execution, and `GOTO_XYZ` planning (requires `MoveIt ON`).
  4. **SERVO:** real-time Cartesian/angular streaming teleoperation via `MoveIt Servo` (requires `Servo ON`).

---

## 8. Web UI 2.0 and 3D Digital Twin

The frontend lives in [`Infrastructure_as_Code/web_ui_2.0`](Infrastructure_as_Code/web_ui_2.0/README.md) (see its local README for full technical details):

* **HTTP Server (`smart_server/web_server.py`):** Multi-threaded `_ThreadingWebServer` (port `8080`, in-memory gzip & cache headers) serving `web_ui_2.0/dist` and workspace ROS assets at `/packages/<pkg>/`, `/install/`, and `/src/`.
* **Map Transport:** [`map_to_image.py`](smart_server/smart_server/map_to_image.py) and `radiation_field_server.py` stream maps over `/map_image/compressed` and `/radiation_image/compressed` as PNGs with atomic geometry metadata packed in `header.frame_id` (`map|res|ox|oy|oz|qx|qy|qz|qw`).
* **3D Engine (`Three.js` + `urdf-loader` + `SimpleTFClient`):**
  * Client-side TF2 resolver without `ros3djs` or `tf2_web_republisher`.
  * Renders robot URDF, 2D occupancy map, semi-transparent radiation layer, SDF environment STL meshes (`sdf_visualizer`), `/plan` paths, `/smart_waypoints_markers`, Shadow twin, and 3D end-effector trail.
  * Drag-oriented **Nav Goal** (right-click / touch), **Center & Follow** camera mode, and an optional on-screen **Touch Joystick** for tablets/mobile browsers.

---

## 9. Unified Command Bus (`/smart_command`) and Telemetry (`/smart_telemetry`)

Message definitions: `smart_interfaces/msg/SmartCommand` (`target_system`, `command`, `payload_json`) and `smart_interfaces/msg/SmartTelemetry`.

### System, Missions, and Subsystems (`target_system: "system"`)

| Command (`command`) | Description | Handler |
|---|---|---|
| `start:<mode>:<map>` / `stop` / `restart` | Start/stop/restart `bringup_<mode>.launch.py` (`lifelong` or `mapping`) | `mission_manager` |
| `start_213`, `start_shelter_zero`, `start_shelter`, `start_kitchen`, `start_mapping`, `start_freeride` | Quick mission launch presets | `mission_manager` |
| `save_map:<name>` | Save `.posegraph` + 2D grid map (and autosave active radiation map) | `mission_manager` |
| `clear_costmaps` / `toggle_slam` | Clear local/global costmaps or pause SLAM Toolbox | `mission_manager` |
| `set_speed:<m/s>` | Dynamically adjust Nav2 speed limit (`FollowPath.vx_max`) | `mission_manager` |
| `watchdog_on` / `watchdog_off` | Enable/disable operator heartbeat & comms watchdog | `heartbeat_pub`, `safety_watchdog` |
| `shadow_on` / `shadow_off` | Activate/deactivate Shadow Mode on the server | `mission_manager`, `twin_orchestrator` |
| `rad_start`, `rad_on`, `rad_off` | Launch/enable/disable radiation subsystem and costmap layer | `mission_manager`, `radiation_manager` |
| `rad_geiger_on` / `rad_geiger_off` | Enable/disable simulated `/virtual_geiger` publisher | `radiation_manager` |
| `rad_load:<name>`, `rad_source:<name>` | Load `.npy` field map or virtual sensor ground-truth map | `radiation_manager` |
| `rad_record:<name>`, `rad_save`, `rad_stop`, `rad_clear` | Start recording, save, stop recording, or clear radiation map | `radiation_manager` |
| `arm_moveit_on` / `arm_moveit_off` | Start/stop `arm_moveit.launch.py` (MoveIt 2 + `control_hub`) | `twin_orchestrator` |
| `arm_servo_on` / `arm_servo_off` / `arm_off` | Start/stop `arm_servo.launch.py` or shut down both arm backends | `twin_orchestrator` |

### Navigation and Waypoints (`target_system: "nav"` / `"waypoints"` / `"radiation"`)

| `target_system` | Command (`command`) | `payload_json` | Handler |
|---|---|---|---|
| `nav` | `go_to` / `go_to_with_bt` | `{"x": 1.0, "y": 2.0, "yaw": 0.5, "laps": 1, "name": "..."}` | `nav_coordinator` |
| `nav` | `waypoints` / `patrol` / `follow_route` | `{"points": [[x,y,yaw], ...], "laps": 1, "name": "..."}` | `nav_coordinator` |
| `nav` | `add_to_route` / `start_route` / `clear_route` | `{"x": .., "y": .., "yaw": ..}` (for `add_to_route`) | `nav_coordinator` |
| `nav` | `cancel` / `resume` / `rth` | for `rth`: `{"x": 0.0, "y": 0.0, "yaw": 0.0}` | `nav_coordinator` |
| `nav` | `go_to_named` | `{"name": "point_name", "laps": 1}` | `waypoint_manager` -> `nav_coordinator` |
| `nav` | `recover_localization` | `{"map": "..."}` (optional) | `recovery_relocalizer` |
| `waypoints` | `save` / `delete` | `{"name": "...", "tab": "...", "x":.., "y":.., "yaw":..}` or `"points": [...]` | `waypoint_manager` |
| `radiation` | `rad_on`, `rad_off`, `rad_geiger_*`, `rad_load`, ... | — (colon-suffixed commands also accepted on `"radiation"`) | `radiation_manager` |

### Operator, Payload, and Tactical (`"operator"` / `"payload"` / `"tactical"`)

| `target_system` | Command (`command`) | `payload_json` | Handler |
|---|---|---|---|
| `operator` | `execute` / `clear` | — (dispatches/clears Shadow Twin route) | `twin_orchestrator` -> `shadow_teleop_*` |
| `operator` | `RESUME` | — (exits `SAFE_HOLD` once comms recover) | `safety_watchdog` |
| `payload` | `mock_sample` | — (simulated `lfcm_drill` sampling cycle) | `payload_manager` |
| `tactical` | `move_relative` | `{"direction": "forward", "distance": 1.0}` | `tactical_executor` |
| `tactical` | `turn_relative` | `{"degrees": 90.0}` | `tactical_executor` |
| `tactical` | `track_target` | `{"offset": -0.2}` | `tactical_executor` |
| `tactical` | `stop` / `cancel` / `abort` | — | `tactical_executor` |

---

## Additional Documentation

* Frontend Technical Reference: [`Infrastructure_as_Code/web_ui_2.0/README.md`](Infrastructure_as_Code/web_ui_2.0/README.md)
* Codebase Changelog: [`Infrastructure_as_Code/CHANGELOG.md`](Infrastructure_as_Code/CHANGELOG.md)
* License: [`LICENSE`](LICENSE)
