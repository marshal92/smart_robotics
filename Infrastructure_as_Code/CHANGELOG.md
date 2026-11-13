# Codebase Changelog

Concise log of codebase changes, recording dates, modified components, and technical rationale.

---

## [2026-11-09]

### 1. `smart_plugins` / `smart_control` / `smart_ai`: Migration of `nav_coordinator` to C++ and `SmartCommand` Handler Hardening
* **Files:**
  * `smart_plugins/src/nav_coordinator.cpp` *(new C++ node)*
  * `smart_plugins/CMakeLists.txt`, `smart_plugins/package.xml`
  * `smart_control/launch/control_core.launch.py`
  * `smart_control/smart_control/nav_coordinator.py`
  * `smart_control/smart_control/waypoint_manager.py`
  * `smart_control/smart_control/tactical_executor.py`
  * `smart_ai/smart_ai/spatial_projector_node.py`
* **Changes:**
  1. **Rewrote `nav_coordinator` in C++ (`smart_plugins/src/nav_coordinator.cpp`):**
     * Ported all Sliding Window logic (`NavigateThroughPoses` / `NavigateToPose`), task queue, `LAPS`, route accumulator (`add_to_route`/`start_route`), and `RESUME` snapshot handling from Python (`BasicNavigator` with two nodes and continuous `spin_once`) to a native asynchronous `rclcpp_action::Client`.
     * Switched `control_core.launch.py` to launch the C++ binary `smart_plugins/nav_coordinator` (updated Python version retained in `smart_control` as fallback).
  2. **Malformed JSON and invalid payload guards:**
     * In `nav_coordinator` (C++ & Python) and `tactical_executor.py`, JSON parse errors or non-object payloads immediately reject the command (`return`) instead of defaulting to driving toward `(0, 0)` or `1.0 m` forward.
     * Added checks for required coordinates (`x`, `y`), numeric finiteness (`std::isfinite` / `math.isfinite`), `points` list structure, and upper bounds (`laps` <= `100`, `points` <= `500`).
  3. **Target filtering in `waypoint_manager.py` before JSON parsing:**
     * `msg.target_system in ('waypoints', 'nav')` is checked at the start of `command_cb` before inspecting `payload`, preventing `AttributeError` on unrelated commands.
  4. **Safe `cancel`, `rth`, and `resume` handling:**
     * Replaced `nav_queue`-based cancellation with a `cancel_requested` flag so rapid `cancel` + `rth` cannot wipe the `rth` goal. `rth` now always cancels any active Nav2 goal first.
     * `resume` is rejected while in `WARNING` or `EVACUATING`, and resumed queued tasks wait until safety FSM enters `NORMAL` / `DISABLED`.
  5. **Aligned stop semantics across `tactical_executor` and `smart_ai`:**
     * `tactical_executor.py` now stops immediately on global `system:stop`, `system:start_freeride`, `system:restart`, as well as `nav:cancel` and `nav:rth` (from `safety_watchdog`).
     * `spatial_projector_node.py` emits `tactical:stop` instead of global `system:stop` when acquiring a target during rotation search.
* **Rationale:**
  * Moving `nav_coordinator` to C++ eliminates Python interpreter and dual-`spin_once` loop overhead, while strict `SmartCommand` validation ensures safe robot behavior on malformed payloads or emergency FSM transitions.

---

### 2. `smart_radiation_plugins` / `smart_plugins` / `smart_radiation` / `web_ui_2.0`: C++ Radiation Package Extraction, Threshold Config, and UI Virtual Dosimeter Toggle
* **Files:**
  * `smart_radiation_plugins/*` *(new package: `radiation_layer.cpp`, `radiation_mapper_node.cpp`, `virtual_geiger_node.cpp`, `alara_speed_reflex.cpp`)*
  * `smart_plugins/CMakeLists.txt`, `smart_plugins/package.xml` *(retains only `telemetry_mux` and `stabilized_frame_publisher_node`)*
  * `smart_radiation/config/radiation_params.yaml` *(new config)*
  * `smart_radiation/smart_radiation/radiation_field_server.py`, `smart_radiation/smart_radiation/radiation_manager.py`, `smart_radiation/smart_radiation/view_map.py`, `smart_radiation/smart_radiation/generate_map.py`, `smart_radiation/smart_radiation/ground_truth_logger.py`
  * `smart_radiation/launch/radiation_bringup.launch.py`, `smart_radiation/setup.py`, `smart_radiation/package.xml`
  * `smart_nav/config/nav2_params.yaml`, `smart_nav/package.xml`
  * `Infrastructure_as_Code/web_ui_2.0/src/components/teleop/TeleopTabs.vue`
* **Changes:**
  1. **Extracted `smart_radiation_plugins` package:** Moved all radiation C++ components (`smart_radiation_plugins::RadiationLayer`, `radiation_mapper_node`, `virtual_geiger_node`, `alara_speed_reflex_node`) out of `smart_plugins` into a dedicated package aligned with `Asymmetric-radiation`. Added `max_cost` ($C_{\max}$, default `220`) to `RadiationLayer` and `smart_nav/config/nav2_params.yaml`. `smart_plugins` now holds core robot nodes only (`telemetry_mux`, `stabilized_frame_publisher_node`).
  2. **Synced with `Asymmetric-radiation`, restored `radiation_map.npy`, and cleaned paths:** Restored reference map `radiation_map.npy` (`800x1200`), which had previously been overwritten by the older mapper (`800x800`). Updated `view_map.py` cost cap to `220` and removed hardcoded `install/... -> src/smart_robotics/...` string replacements.
  3. **Dynamic thresholds and `radiation_params.yaml`:** Exposed `d_noise`, `d_crit`, and `k` in `radiation_field_server.py` as dynamic ROS 2 parameters (recomputing the cost grid live via `ros2 param set`) backed by `smart_radiation/config/radiation_params.yaml` and auto-loaded in `radiation_bringup.launch.py`.
  4. **Explicit virtual dosimeter toggle (`rad_geiger_on` / `rad_geiger_off`):** Activating the field (`rad_on`) no longer forces `virtual_geiger` on automatically. Separate commands (`Virt Geiger ON` / `Virt Geiger OFF`) prevent conflicts when attaching a physical dosimeter to `/radiation/dose`.
  5. **Web UI update (`TeleopTabs.vue`):** Moved `Rad Map ON` / `Rad Map OFF` from `Manager` tab to `Radiation` tab and added `Virt Geiger ON`, `Virt Geiger OFF`, and `Rad Stop` controls.
* **Rationale:**
  * Prepares `smart_radiation` + `smart_radiation_plugins` cleanly for standalone extraction, enables threshold tuning without extra telemetry traffic, and allows conflict-free switching between simulated and physical dosimeters.

---

### 3. `smart_radiation` / `smart_control` / `smart_master` / `smart_plugins`: Radiation Subsystem Isolation & Modularity
* **Files:**
  * `smart_radiation/smart_radiation/radiation_manager.py` *(new node)*
  * `smart_radiation/launch/radiation_bringup.launch.py`, `smart_radiation/setup.py`
  * `smart_radiation/smart_radiation/radiation_field_server.py`, `smart_radiation/smart_radiation/baseline_field_server.py`
  * `smart_plugins/src/radiation_mapper_node.cpp`, `smart_plugins/src/virtual_geiger_node.cpp`
  * `smart_control/smart_control/mission_manager.py`
  * `smart_master/launch/sim_master.launch.py`, `smart_master/launch/real_master.launch.py`
  * `Infrastructure_as_Code/autostart/start_server.sh`, `Infrastructure_as_Code/autostart/start_robot.sh`
* **Changes:**
  1. **Disabled radiation autostart:** Removed `radiation_bringup` from `sim_master.launch.py` and `real_master.launch.py`.
  2. **Encapsulated control in `radiation_manager`:** Removed direct radiation service clients (`/radiation_mapper`, `/radiation_field_server`, `/virtual_geiger`) and `.npy` / `/dev/shm` paths from `mission_manager.py`. Centralized `rad_on`, `rad_off`, `rad_load:<name>`, `rad_record:<name>`, `rad_save`, `rad_stop`, `rad_clear` in `radiation_manager.py`.
  3. **On-demand launch (`rad_on` / `rad_start`):** `mission_manager` starts `radiation_bringup.launch.py` inside a dedicated `radiation_session` tmux session on first request without restarting SLAM/Nav2 or duplicating processes; subsequent `rad_off` / `rad_on` toggles sleep/wake nodes via `radiation_manager`.
  4. **Virtual sensor map control, shared `maps_dir`, and conflict guard:**
     * Unified `maps_dir` parameter (`~/ros2_ws/src/smart_robotics/smart_radiation/maps`).
     * `rad_load:<name>` (when `<name> != explored_map.npy` and no manual `rad_source:<name>` override is active) synchronously updates both field server and `virtual_geiger`. `rad_record:explored_map.npy` writes into `explored_map.npy` while keeping `virtual_geiger` on `sensor_map_path` (`radiation_map_complex.npy`).
     * `virtual_geiger_node.cpp` mutes itself whenever `count_publishers("/radiation/dose") > 1`; `mission_manager.py` inspects ROS 2 graph node names before spawning `radiation_session`.
  5. **Weight grid loading fix in C++ mapper:** When loading a differently sized map without a weights file, `weight_grid_` is sized strictly to the loaded map dimensions with size compatibility checks.
  6. **`/radiation/status` telemetry:** Publishes readiness, active map name, recording status, and errors after service completion.
* **Rationale:**
  * Achieves full modularity: `smart_control` treats radiation as a black box lifecycle session while `smart_radiation` encapsulates all map, dosimeter, and penalty logic.

---

### 4. `smart_control`: Zero-Idle Operation and Collision Fixes in `tactical_executor`
* **Files:**
  * `smart_control/smart_control/tactical_executor.py`
* **Changes:**
  1. In `IDLE` state, only `/smart_command` remains subscribed (`/odom`, `/scan` subscriptions and timers are torn down for 0.0% CPU).
  2. Added 0.5 s watchdog timer for `track_target` and safety timeouts for `move_relative` / `turn_relative`.
  3. Cached LiDAR beam indices ($\pm 20^\circ$) with immediate stop in `scan_cb`.
  4. Moved status topic from `/smart_telemetry` to `/tactical/status` (`std_msgs/msg/String`).
* **Rationale:**
  * Eliminates DDS collision with `telemetry_mux` and guarantees zero background Raspberry Pi CPU usage when idle.

---

## [2026-11-09] — Migration of `nav_coordinator` and Manipulator Nodes (`teleop_manager`, `tactical_server`, `control_hub`) to C++ (Zero-Idle)

### 1. `smart_plugins`, `smart_control`, `smart_ai`: C++ `nav_coordinator` Rewrite & `SmartCommand` Routing Fixes
* **Files:**
  * `smart_plugins/src/nav_coordinator.cpp`, `smart_plugins/CMakeLists.txt`, `smart_plugins/package.xml`
  * `smart_control/launch/control_core.launch.py`, `smart_control/smart_control/nav_coordinator.py`
  * `smart_control/smart_control/waypoint_manager.py`, `smart_control/smart_control/tactical_executor.py`
  * `smart_ai/smart_ai/spatial_projector_node.py`
* **Changes:**
  1. Created native C++ `nav_coordinator` in `smart_plugins` interfacing directly with Nav2 Action servers (`/compute_path_to_pose`, `/follow_path`, `/navigate_to_pose`, `/spin`) without Python `BasicNavigator`.
  2. Fixed `SmartCommand` routing issues (`start_patrol`, `set_goal`, `delete_route`, `track_target`, `move_relative`, `target_class` init).

---

### 2. `manipulator_control`, `smart_moveit_config`: C++ Rewrite of `teleop_manager`, `tactical_server`, `control_hub` & `+X` Workspace Alignment
* **Files:**
  * `manipulator_control/src/teleop_manager.cpp`, `manipulator_control/src/tactical_server.cpp`, `manipulator_control/src/control_hub.cpp`
  * `manipulator_control/CMakeLists.txt`, `manipulator_control/package.xml`
  * `manipulator_control/launch/auto_control.launch.py`, `manipulator_control/manipulator_control/test/square_horizontal.csv`
  * `smart_moveit_config/config/smart_robot.srdf`
* **Changes:**
  1. **`teleop_manager.cpp` (Zero-Idle):** 50 Hz servo timer runs only during active motion and cancels when idle (`servo_timer_->cancel()`); TF lookup for `/web_teleop/tool_pose` runs only when subscribers exist; added 10 s watchdog and `unfold` interlock in `AUTO` mode.
  2. **`tactical_server.cpp`:** Native C++ `manipulator_action` Action server wrapping `/move_action`, `/compute_cartesian_path`, and `/execute_trajectory` without `time.sleep` polling or GIL stalls.
  3. **`control_hub.cpp` (Zero-Idle):** Removed `/tf` `TransformListener` subscription — start pose is computed via `/compute_fk` on task start only; added RAII guard on `is_executing_`.
  4. **Config & coordinates:** Updated `virtual_joint` (`child_link="base_footprint"`), SRDF collision matrix, `auto_control.launch.py`, and `+X`-aligned `square_horizontal.csv` path.
* **Rationale:**
  * Eliminated ~207% idle CPU load from the three Python manipulator nodes while preserving full compatibility with existing launch files and web UIs.

---

### 3. `smart_plugins`, `manipulator_control`, `smart_server`, `smart_master`: C++ `trajectory_bridge`, Unified `arm_backend.launch.py`, Web UI Control via `twin_orchestrator`, and Zenoh Rules
* **Files:**
  * `smart_plugins/src/trajectory_bridge.cpp`, `manipulator_control/src/trajectory_bridge.cpp`
  * `smart_plugins/CMakeLists.txt`, `smart_plugins/package.xml`, `manipulator_control/CMakeLists.txt`
  * `smart_server/launch/arm_backend.launch.py`, `smart_server/launch/server.launch.py`, `smart_server/smart_server/twin_orchestrator.py`
  * `smart_master/launch/real_master.launch.py`
  * `Infrastructure_as_Code/autostart/start_robot.sh`, `Infrastructure_as_Code/autostart/start_server.sh`
  * `Infrastructure_as_Code/web_ui_2.0/src/components/teleop/ArmControl.vue`
* **Changes:**
  1. **C++ `trajectory_bridge` (Action + Topic):** Added C++ node supporting both `/arm_controller/follow_joint_trajectory` actions (with immediate Cancel preemption) and `/arm_controller/joint_trajectory` topic commands (used by sliders, `Unfold`, and `moveit_servo`). Wired into `real_master.launch.py` under `use_arm:=true`.
  2. **Unified `arm_backend.launch.py`:** Integrated `move_group` with automatic `use_sim_time` forwarding and `use_rviz:=false` by default.
  3. **`twin_orchestrator` manipulator lifecycle:** Added `arm_on`, `arm_on_rviz`, and `arm_off` commands managing tmux `arm_session` on the server, plus `MoveIt ON` / `MoveIt OFF` / `Unfold` UI controls.
  4. **Zenoh Bridge allowlist:** Added `^rt/arm_joint_states$`, `^rt/arm_controller/joint_trajectory$`, and `^.*/arm_controller/follow_joint_trajectory/.*$` to `start_robot.sh` and `start_server.sh`.
  5. **Unified Operator Launcher (`smart_launcher.py`) & Cleanup:**
     * Added PyQt6 + `QWebEngineView` launcher (`Infrastructure_as_Code/autostart/smart_launcher.py` and `~/smart_launcher.py`) with `Simulation` and `Real Robot` modes, `.sdf` auto-discovery, and embedded Web UI dashboard.
     * Added `USE_ARM=${1:-false}` argument propagation in `start_robot.sh` and `start_server.sh`.
     * Removed legacy launch files `moveit_client.launch.py`, `moveit_real_client.launch.py`, `arm_moveit_sim.launch.py` from `smart_server/launch/`.
     * Standardized comments and log output to English.
  6. **Launcher UI Ergonomics (Fullscreen & Collapsible Bar):**
     * Added collapsible top toolbar (`▲ Hide Bar (F10)` / `F10`, floating `▼ Bar (F10)` overlay button).
     * Enabled `FullScreenSupportEnabled` and `fullScreenRequested` handling (`F11` / `Escape` / toolbar `⛶ Fullscreen` / Web UI `⛶`).
     * Removed `Initial Spawn Pose` widgets from launcher UI for a compact layout.
  7. **Desktop Launcher ROS 2 Environment Fix:**
     * **Root cause:** GNOME desktop launches skip `~/.bashrc`, omitting `CYCLONEDDS_URI` (`MaxAutoParticipantIndex=500`), causing Nav2 (`collision_monitor`) to hit the default ~10 participant limit when started from `mission_manager`.
     * **Fix:** `smart_launcher.py` loads the interactive shell environment (`bash -ic`) at startup and propagates it to spawned `tmux` sessions without modifying `mission_manager.py`.
