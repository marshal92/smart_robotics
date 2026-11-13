# Smart Robotics Web UI 2.0 (Supervisory HMI)

Browser-based ROS 2 **Supervisory Human–Machine Interface (HMI)** for the Smart Robotics platform. Built with Vue 3, Pinia, native Three.js, and `roslib`, it provides unified telemetry monitoring, real-time 3D digital-twin visualization, Nav2 navigation & waypoint mission orchestration, radiation field mapping, Shadow Mode trajectory previewing, live video/YOLO inspection, and 6-DOF manipulator teleoperation & sequencing.

---

## Table of Contents

1. [Architecture & Technology Stack](#1-architecture--technology-stack)
2. [Performance Engineering](#2-performance-engineering)
3. [Project Structure & Module Reference](#3-project-structure--module-reference)
4. [Workspace Layout, Themes & Responsive Modes](#4-workspace-layout-themes--responsive-modes)
5. [3D Digital Twin & Map Interaction](#5-3d-digital-twin--map-interaction)
6. [Operator Subsystems](#6-operator-subsystems)
7. [ROS 2 & HTTP Interface Contract](#7-ros-2--http-interface-contract)
8. [URDF, Mesh & 3D Asset Pipeline](#8-urdf-mesh--3d-asset-pipeline)
9. [Browser Persistence (`localStorage`)](#9-browser-persistence-localstorage)
10. [Development, Build & Deployment](#10-development-build--deployment)
11. [Known Constraints & Technical Debt](#11-known-constraints--technical-debt)

---

## 1. Architecture & Technology Stack

| Layer | Technology / Package | Role |
|---|---|---|
| **UI Framework** | `vue@^3.5.40` (`<script setup>`) | Reactive single-page HMI layout and subsystem panels |
| **State Store** | `pinia@^4.0.2` (`useRosStore`) | Centralized connection state, telemetry, waypoints, queues, logs, arm trail flags |
| **Build Tooling** | `vite@^8.2.0`, `@vitejs/plugin-vue@^6.0.8` | ESM bundling to `dist/` and Hot Module Replacement dev server (`:5173`) |
| **ROS 2 Bridge** | `roslib@^2.1.0` + `rosbridge_websocket` | JSON-over-WebSocket pub/sub and ROS 2 service client (`ws://<host>:9090`) |
| **3D Engine** | `three@^0.164.0` + `urdf-loader@^0.13.1` | Native WebGL digital twin (`ros3djs` removed), STL loading, OrbitControls, raycasting |
| **TF Engine** | Custom `SimpleTFClient` | Direct client-side transform tree resolution over `/tf` and `/tf_static` |
| **Styling** | Vanilla CSS (`src/style.css`) | CSS custom-property design system with Dark Instrumental & Academic Light CAD themes |
| **Production Server** | `smart_server/web_server.py` (port `8080`) | Serves `web_ui_2.0/dist` plus allowlisted ROS 2 package assets (`/packages`, `/install`, `/src`) |

```text
  Browser (Web UI 2.0)
   ├── HTTP :8080  ──▶ smart_server/web_server.py ──▶ dist/, /packages/<pkg>/, /install/
   └── WS   :9090  ──▶ rosbridge_websocket        ──▶ ROS 2 Graph
                                                       ├── UGV / Nav2 (nav_coordinator, waypoint_manager)
                                                       ├── Orchestration (twin_orchestrator, shadow_teleop)
                                                       ├── Vision & Map (map_to_image, camera / YOLO)
                                                       └── Manipulator (teleop_manager, control_hub, tactical_server, moveit_servo)
```

---

## 2. Performance Engineering

Web UI 2.0 was specifically engineered to prevent main-thread stalls, WebSocket saturation, and GPU memory leaks during multi-hour teleoperation and SLAM mapping:

1. **Zero-GC Client-Side TF Resolution (`src/services/simpleTfClient.js`)**
   * Replaces `ROSLIB.TFClient` and removes the backend `tf2_web_republisher` dependency.
   * Subscribes directly to `/tf` and `/tf_static`, resolving transform chains back to `fixedFrame` (`map`, max hop guard `20`).
   * Reuses pre-allocated `THREE.Vector3` and `THREE.Quaternion` scratch instances during traversal to avoid per-frame garbage collection churn, and batches subscriber notifications into a single `requestAnimationFrame` pass when new transforms arrive.

2. **Atomic PNG Transport for Costmaps & Radiation (`useMapLayer.js`, `useRadiationMap.js`)**
   * Instead of serializing large `nav_msgs/msg/OccupancyGrid` arrays over WebSocket JSON, [`map_to_image.py`](../../smart_server/smart_server/map_to_image.py) flips and encodes a single-channel grayscale PNG on `/map_image/compressed` (`hash`-cached when unchanged).
   * Map geometry metadata is embedded atomically inside `msg.header.frame_id`:
     ```text
     map|<resolution>|<origin.x>|<origin.y>|<origin.z>|<quat.x>|<quat.y>|<quat.z>|<quat.w>
     ```
   * This prevents visual tearing or misalignment between map pixels and world coordinates when SLAM dynamically expands map dimensions. When resolution or pixel dimensions are stable, `useMapLayer` swaps only `texture.image` without reallocating the WebGL `PlaneGeometry` or `THREE.Texture`.

3. **Scoped Throttling & Lazy Media Subscriptions**
   * **Camera stream (`CameraStream.vue`)**: Subscribes to compressed JPEG topics only while mounted (`onMounted`), switches cleanly between RAW and YOLO streams, and immediately unsubscribes on unmount (`onBeforeUnmount`).
   * **URDF joint animation (`robotModel.js`)**: Throttled to `~30 Hz` (`33 ms` minimum interval); UI joint slider feedback in `ArmControl.vue` is throttled separately to `10 Hz` (`100 ms`).
   * **3D coordinate readout & raycasting (`DigitalTwin3D.vue`)**: Robot pose HUD reactivity throttles to `10 Hz` (`100 ms`), while cursor hover raycasting onto the map plane throttles to `20 Hz` (`50 ms`).
   * **Signature-cached waypoint markers (`useWaypoints.js`)**: Hashes each marker pose/color/label (`userData.sig`) so unchanged markers only toggle `.visible` instead of rebuilding Canvas sprite textures and cylinder geometries.

4. **Deterministic GPU & Async Cleanup**
   * `createViewer.js` caps pixel ratio at `Math.min(window.devicePixelRatio, 1.5)` and tears down the `requestAnimationFrame` loop, `ResizeObserver`, `OrbitControls`, and WebGL context on unmount.
   * `useMapLayer.js`, `useRadiationMap.js`, and `useSdfWorlds.js` increment generation counters (`generation` / `loadGeneration`) so delayed HTTP fetches or image `onload` callbacks from prior sessions are discarded without touching disposed scenes.
   * `robotModel.js`, `armTrail.js`, and `DigitalTwin3D.vue` explicitly dispose geometries, materials, textures, and event listeners on ROS disconnect or unmount.

---

## 3. Project Structure & Module Reference

```text
web_ui_2.0/
├── index.html                               # SPA entry point (loads /src/main.js and /favicon.svg)
├── package.json                             # Dependencies: vue, pinia, roslib, three, urdf-loader, vite
├── vite.config.js                           # Minimal Vite config (@vitejs/plugin-vue; no dev proxy)
├── build_ui.sh                              # Helper script sourcing $HOME/.nvm before `npm run build`
├── fix-web-ui-haze.patch                    # Legacy ros3djs patch retained for historical reference (unused)
├── README.md                                # This technical reference
├── dist/                                    # Compiled production assets served directly by smart_server/web_server.py
└── src/
    ├── main.js                              # Creates Vue app + Pinia store and mounts to #app
    ├── App.vue                              # Root layout shell, responsive bar (<=1024px), collapsible 125px bottom dock
    ├── style.css                            # Shared CSS design tokens (dark & light CAD themes), shared button/input classes
    ├── stores/
    │   └── rosStore.js                      # Pinia store (`useRosStore`): ROS state, telemetry, waypoints, queues, arm trail
    ├── services/
    │   ├── rosConnection.js                 # ROSLIB singleton, /smart_command, /smart_telemetry, /cmd_vel*, camera & logs
    │   ├── simpleTfClient.js                # Client-side TF2 chain solver subscribing to /tf & /tf_static
    │   └── teleopCore.js                    # 10 Hz Twist loop combining DPad keyboard/buttons & TouchJoystick analog input
    ├── three/
    │   ├── createViewer.js                  # Z-up Three.js scene, camera, lighting, OrbitControls, ResizeObserver
    │   ├── robotModel.js                    # Fetches robot_description, parses URDF/STL, animates joints & TF root
    │   └── armTrail.js                      # Live cyan TCP trail (max 1500 pts) + dashed amber planned trajectory
    └── components/
        ├── layout/
        │   ├── AppHeader.vue                # Brand, CAD light/dark toggle, TelemetryHUD, ConnectionBox, global STOP
        │   ├── TelemetryHUD.vue             # Monospace HUD: FSM, VEL, RAD, NAV, LIGHT state
        │   ├── ConnectionBox.vue            # Dynamic ws://<hostname>:9090 input/pill & connection state badge
        │   ├── DigitalTwin3D.vue            # 3D canvas host, Center Camera, Nav Goal drag arrow, Shadow twin & paths
        │   ├── NavPopup.vue                 # Floating waypoint overlay (CANCEL, RESUME, named go_to_named triggers)
        │   └── composables/
        │       ├── useMapLayer.js           # /map_image/compressed -> PlaneGeometry + dynamic PNG texture
        │       ├── useRadiationMap.js       # /radiation_image/compressed -> translucent overlay layer (+0.005 m Z)
        │       ├── useSdfWorlds.js          # Parses SDF XML + loads STL world environments with adjustable opacity
        │       ├── useWaypoints.js          # Renders /smart_waypoints_markers cylinders & Canvas text sprites
        │       └── useNavSpeed.js           # Publishes `system` -> `set_speed:<m/s>` (0.1–2.0 m/s)
        ├── teleop/
        │   ├── TeleopTabs.vue               # Right control pane: Manager, Teleop, Arm, Radiation tabs
        │   ├── ArmControl.vue               # Modular 6-DOF manipulator shell: Unfold/Fold/3D Trail + JOINTS/MANUAL/AUTO/SERVO tabs
        │   ├── arm/
        │   │   ├── useArmRos.js             # Shared ROS topic/action composable & hybrid FK/TF pose telemetry for arm tabs
        │   │   ├── armKinematics.js         # URDF 3D FK, 2D cylindrical boom DLS Jacobian & J3/J5 roll compensation
        │   │   ├── armPanel.css             # Shared styles across ArmControl sub-tabs
        │   │   ├── ArmJointsTab.vue         # J0..J5 direct sliders, presets & Joint Route Sequencer
        │   │   ├── ArmManualTab.vue         # Cylindrical 2.5D manual kinematics (DLS R/Z, auto-level J4, J3+J5)
        │   │   ├── ArmAutoTab.vue           # MoveIt ON/OFF, Control Hub CSV missions, GOTO_XYZ & execution logs
        │   │   └── ArmServoTab.vue          # Servo ON/OFF, Cartesian IK D-Pad & PITCH/ROLL/YAW teleop
        │   ├── DPad.vue                     # Base/Shadow directional pad + global WASD / Arrow-key teleop bindings
        │   ├── SpeedSlider.vue              # Vertical linear/angular velocity slider (0.1–2.0 m/s, synced with TouchJoystick)
        │   ├── TouchJoystick.vue            # Toggleable floating 3D analog touch joystick with pointer capture & deadzone
        │   ├── QuickActions.vue             # Bottom dock Actions, LAPS selector, Queue Mode & named waypoint grid
        │   └── CameraStream.vue             # Lazy compressed image viewer with RAW / YOLO toggle & fullscreen
        ├── mission/
        │   ├── MissionManager.vue           # Wrapper mounting WaypointCreator (`activeMissionTab="global"`)
        │   └── WaypointCreator.vue          # Form to save single named points or multi-point routes via /smart_command
        ├── console/
        │   └── RosConsole.vue               # Rolling 50-line /rosout terminal view with severity coloring
        └── mechanisms/
            └── MechanismsPanel.vue          # Legacy unimported placeholder component for LED light control
```

---

## 4. Workspace Layout, Themes & Responsive Modes

### Top Header (`AppHeader.vue`)
* **Height:** Fixed `42px` on desktop (`flex-wrap` auto-height at `<= 768px`).
* **Theme Switcher (`Theme ◐`):** Toggles `html.light-theme` / `data-theme="light"`, persists to `localStorage['theme']`, and dispatches a custom `theme-changed` window event so `DigitalTwin3D.vue` updates the WebGL clear color between `0x0f1115` (dark) and `0xe2e8f0` (Academic Light CAD).
* **Telemetry HUD (`TelemetryHUD.vue`):** Tabular monospace readout of:
  * `FSM` (color-coded: `NORMAL` green, `WARNING` orange, `EVACUATING` red, `SAFE_HOLD` blue, `DISABLED` muted, `UNKNOWN`/other accent)
  * `VEL` (m/s, zero-deadband `< 0.005`)
  * `RAD` (µSv/h, zero-deadband `< 0.005`)
  * `NAV` (status string from `/smart_telemetry`)
  * `LIGHT` (status indicator synced to `store.lightOn`)
* **Connection Box (`ConnectionBox.vue`):** Initializes `wsUrl` automatically from `ws://${window.location.hostname || '127.0.0.1'}:9090`. Once connected, collapses into a clickable status pill (`● ws://...`) allowing runtime reconnection to another bridge address.
* **Global `🛑 STOP`:** Dispatches `{ target_system: 'nav', command: 'cancel', payload_json: '{"x":0,"y":0,"yaw":0}' }` and zero velocity on `/cmd_vel`.

### Responsive Layout (`App.vue`)
* **Desktop (`> 1024px`):** Split workspace with flexible 3D viewport on the left and fixed `504px` panel (`TeleopTabs.vue`) on the right.
* **Compact / Tablet (`<= 1024px`):** Displays a `28px` switcher bar with three modes (`Split View`, `3D View`, `Controls`), dispatching a window `resize` event on tab change so Three.js camera aspect and renderer dimensions recompute immediately.
* **Bottom Collapsible Dock:** Expandable `125px` panel housing **Actions & Navigation** (`QuickActions.vue`), **Waypoint Creator** (`MissionManager.vue`), and **ROS Console** (`RosConsole.vue`) with a live message badge.

---

## 5. 3D Digital Twin & Map Interaction

Configured in `src/three/createViewer.js` and orchestrated by `src/components/layout/DigitalTwin3D.vue`:

* **Scene Conventions:** Z-up (`camera.up.set(0, 0, 1)`), initial camera `(3, -4, 3)` looking at `(0, 0, 0.3)`, `THREE.SRGBColorSpace`, `THREE.NoToneMapping`, `PCFSoftShadowMap`, and triple lighting (ambient + dual directional lights).
* **OrbitControls:** `LMB` rotate, `MMB` pan, `RMB` dolly/zoom, damping disabled for crisp CAD-style response, `screenSpacePanning = false`.
* **Center & Follow Camera (`toggleFollowAndCenter` / `centerCameraOnRobot`):** Clicking the top-right reticle button toggles **FOLLOW** mode on (immediately centering on `robotGroup.position + (0, 0, 0.3)` while preserving the user's current viewing offset) and translates both `controls.target` and `camera.position` by each TF `base_footprint` delta so users can freely orbit or pinch-zoom around a moving robot. Clicking again exits Follow mode.
* **Live Layers & Overlays:**
  * **SLAM Occupancy Map (`useMapLayer.js`):** Placed at `(origin.x, origin.y, origin.z - 0.005)` with `NearestFilter` sharpness.
  * **Radiation Heatmap (`useRadiationMap.js`):** Placed at `origin.z + 0.005` (`opacity: 0.85`, `depthWrite: false`) and toggled via the **`radiation`** button.
  * **SDF 3D Environments (`useSdfWorlds.js`):** Fetches `<world>.sdf` over HTTP (`213`, `kitchen`, `shelter_zero`, `shelter_zero_empty`, `shelter_zero_map`), parses `<model>`, `<link>`, and `<visual>` ZYX Euler poses + STL meshes, and adjusts transparency dynamically via the `10%–100%` opacity slider (`3D ▾`). Automatically loads `213` on ROS connect.
  * **Waypoints (`useWaypoints.js`):** Subscribes to `/smart_waypoints_markers`, creating cylinders (`Marker.CYLINDER = 3`) and black-outlined floating labels (`Marker.TEXT_VIEW_FACING = 9`, `THREE.Sprite`, `alphaTest: 0.5`).
  * **Planned Paths & Shadow Mode:**
    * Nav2 path (`/plan`): orange line elevated to `Z + 0.02`.
    * Shadow planned path (`/shadow_path`): cyan line elevated to `Z + 0.03`.
    * Shadow robot mesh: loads `base.STL`, attached to `shadow_base_link` TF frame, dynamically tinted/hidden via `/shadow_marker` RGBA and Z threshold (`> -1.0`).
* **Interactive 2D Nav Goal:**
  * Activating the floating target button enables `touch-action: none` on `#viewer3d`, disables `OrbitControls` during pointer capture (`setPointerCapture`), and intercepts `pointerdown`/`pointermove`/`pointerup`/`pointercancel` in the capture phase so both desktop mouse and Android touch-drag work identically.
  * Press/touch + drag raycasts onto `mapPlane` (falling back to the horizontal ground plane at `dragStartPoint.z` if the finger drags past the map PNG boundary) and renders a green directional arrow (`navGoalArrow`); releasing publishes a `geometry_msgs/msg/PoseStamped` goal in frame `map` to `/goal_pose` (a tap/click without drag `<= 0.08 m` preserves the robot's current heading yaw).
* **Bottom Viewport Bar & On-Screen Joystick:** Live hover coordinates (`Cur: X | Y`), live robot base pose (`Rob: X | Y`), toggles for `camera` overlay (`CameraStream`), `NAV` overlay (`NavPopup`), `3D ▾` SDF worlds, `WP`, `radiation`, `SHADOW`, `JOYSTICK` (`TouchJoystick.vue` overlay on the bottom-left), and `velocity ▾` (`0.1–2.0 m/s`).
  * `TouchJoystick.vue` uses pointer capture with a `0.10` normalized deadzone, proportional forward/reverse (`linear.x`) and turn (`angular.z`), an inline `- / +` speed stepper synchronized with `SpeedSlider.vue`, and automatic zero-twist failsafes on pointer release/cancel, window `blur`, tab hide, or component unmount.

---

## 6. Operator Subsystems

### Manager & Radiation (`TeleopTabs.vue`)
* **`Manager` Tab:**
  * Core controls: `TERMINATE` (`system:stop`), `RESUME` (`operator:RESUME`), `Recovery` (`nav:recover_localization`).
  * Scenarios & Maps: `Freeride` (`system:start_freeride`), `GTO Mapping` (`system:start:mapping:none`), preset scenario selector (`start_213`, `start_kitchen`, `start_shelter_zero`), custom lifelong map launcher (`system:start:lifelong:<name>`), and `Save Map` (`system:save_map:<name>`).
  * Safety: `WATCHDOG` toggle (`system:watchdog_on` / `watchdog_off`), state indicator derived live from `telemetry.fsm_state !== 'DISABLED'`.
* **`Radiation` Tab:**
  * Radiation layer & virtual Geiger toggles (`rad_on`/`rad_off`, `rad_geiger_on`/`rad_geiger_off`), synchronized with `/radiation/status` JSON.
  * Survey recording (`rad_record:explored_map.npy`, `rad_stop`, `rad_save`, `rad_clear`) and map presets (`rad_load:<file.npy>`).

### Chassis & Shadow Teleop (`TeleopTabs.vue`, `DPad.vue`, `TouchJoystick.vue`, `SpeedSlider.vue`, `teleopCore.js`)
* **Target Toggle (`BASE` / `SHADOW`):** Routes `/cmd_vel` to the physical/simulated chassis OR `/cmd_vel_shadow` to the virtual Shadow twin. In `SHADOW` mode, exposes quick buttons for `ENABLE` (`shadow_on`), `DISABLE` (`shadow_off`), `CLEAR` (`operator:clear`), and `EXEC` (`operator:execute`).
* **`10 Hz` Velocity Streaming (`teleopCore.js`):** Pressing on-screen `DPad` arrows, keyboard keys (`W/A/S/D` or Arrow keys, automatically ignored when focus is inside `<input>`, `<textarea>`, `<select>`, or `contentEditable`), or dragging the floating 3D `TouchJoystick` (`JOYSTICK` toggle) runs a `100 ms` publish loop using `teleopSpeed` (`0.1–2.0 m/s`, default `0.5 m/s`, synced between `SpeedSlider.vue` and `TouchJoystick.vue`).
* **Motion Safety Failsafes:** Velocity immediately stops on tab switch (`setTab`), `mouseup`, `mouseleave`, `pointerup`, `pointercancel`, `lostpointercapture`, `touchend`, `touchcancel`, `window` blur, key release, or component unmount.

### 6-DOF Manipulator (`ArmControl.vue` & `src/components/teleop/arm/`)
* **Common Header Bar (all sub-tabs, works without MoveIt/Servo):**
  * `Unfold`: Publishes target stand pose `[0, 57.3, -57.3, 0, -45, 0]°` over `3.0 s` to `/arm_controller/joint_trajectory` and triggers `/web_teleop/unfold`.
  * `Fold`: Publishes home pose `[0, 0, 0, 0, 0, 0]°` over `3.0 s` and triggers `/web_teleop/fold`.
  * `3D TRAIL` / `CLEAR`: Toggles or clears the browser-side `ArmTrailManager` TCP path rendered directly from local URDF/TF (`robotModel.js`).
* **`JOINTS` Sub-tab (`ArmJointsTab.vue`) — Tab 1:**
  * Direct sliders + `±5°` step buttons + numeric inputs for `arm_joint_0..5` (`SYNC`, `SAVE` pose, dropdown preset loader, `RUN` with configurable move duration `>= 0.2 s`). Pressing `±5°` syncs all slider values from live `/joint_states` first before stepping the selected joint (`0.5 s` move).
  * **`JOINT ROUTE SEQUENCER`:** Build multi-step joint sequences (`+ ADD TO ROUTE` from sliders/selected pose, or `+ FROM ROBOT` syncing live robot angles), configure per-step move duration (`>= 0.3 s`) and post-move pause (`w`, `s`), reorder (`▲`/`▼`), load any step back to sliders, toggle `LOOP`, and save/load named routes.
  * **Sequential Cancelability:** Each route step is sent sequentially over a cancelable `50 ms`-polled timer as a **single-point** `trajectory_msgs/JointTrajectory` message to `/arm_controller/joint_trajectory`. In [`trajectory_bridge.cpp`](../../smart_plugins/src/trajectory_bridge.cpp), single-point messages dispatch straight to ESP32 servos without spawning a detached `sleep_for` thread, so clicking `⏹ STOP` cancels the wait loop and immediately commands a `0.1 s` hold at current angles.
* **`MANUAL` Sub-tab (`ArmManualTab.vue`) — Tab 2:**
  * Backend-free **cylindrical 2.5D kinematics** executed in-browser (`armKinematics.js`) at `50 ms` ticks (`time_from_start: 0.08 s`) directly onto `/arm_controller/joint_trajectory` with target-state latching on press and strict URDF joint limit clamping.
  * **Boom Control (`R / Z / Yaw`):** `BASE L/R` jogs `arm_joint_0`, while `REACH +/-(FWD/BACK)` and `UP/DOWN (Z±)` solve analytical $2\times 2$ Damped Least Squares ($\lambda = 0.015$) on shoulder/elbow (`arm_joint_1`, `arm_joint_2`, $L_1=0.274\text{ m}$, $L_2=0.216\text{ m}$) with singularity/workspace boundary protection and toggleable **`AUTO-LEVEL WRIST (J4)`** pitch compensation.
  * **Wrist & Tool Control:** `PITCH UP/DOWN` drives `arm_joint_4`, `ROLL L/R` drives `arm_joint_5`, and `WRIST L/R` steers `arm_joint_3` with real-time `arm_joint_5` roll leveling via exact FK Jacobian so the gripper jaws remain parallel to the ground.
* **`AUTO` Sub-tab (`ArmAutoTab.vue`) — Tab 3:**
  * `MoveIt ON` / `MoveIt OFF`: Dispatches `system:arm_moveit_on` / `system:arm_moveit_off` to `twin_orchestrator.py`, managing `arm_moveit_session` (`smart_server/launch/arm_moveit.launch.py`: `move_group` headless without RViz, `tactical_server`, `control_hub`).
  * Publishes `EXECUTE_CSV` with selected CSV path and speed ratio (`5–100%`, default `30%`) to `/web_teleop/hub_request`, displaying progress, `/web_teleop/hub_status` logs, and the dashed amber planned preview in `3D`.
  * **Manual Coordinate Move (`GO TO COORDINATES (BASE, MM)`):** Accepts `X, Y, Z` in millimeters (`SYNC` copies live TCP pose, auto-syncs once when first pose arrives) and sends `{ command: "GOTO_XYZ", x, y, z, speed }` in meters to `/web_teleop/hub_request`.
* **`SERVO` Sub-tab (`ArmServoTab.vue`) — Tab 4:**
  * `Servo ON` / `Servo OFF`: Dispatches `system:arm_servo_on` / `system:arm_servo_off` to `twin_orchestrator.py`, managing `arm_servo_session` (`smart_server/launch/arm_servo.launch.py`: standalone `servo_node` with `is_primary_planning_scene_monitor=True` + `teleop_manager`).
  * **Cartesian IK Jogging:** `X±/Y±/Z±` translation and `PITCH/ROLL/YAW` rotation buttons publish `geometry_msgs/TwistStamped` at `10 Hz` to `/web_teleop/cmd_vel` in `arm_base_link` (`BASE`) or `arm_tool0` (`TOOL`), scaled by `SPEED` (`1–100%`, default `50%`). Releasing any jog control sends zero twist immediately and redundantly `40 ms` later; global release/`blur` listeners prevent runaway jogging.
* **Shared Tool Pose Telemetry (`TOOL POSE TELEMETRY (BASE FRAME)`):**
  * Visible across all tabs even without `servo_node`/`teleop_manager`: uses `/web_teleop/tool_pose` (`LIVE 5Hz`) when Servo telemetry is active, and automatically falls back to browser-side URDF forward kinematics (`computeArmToolFrame` from `/joint_states`, `LIVE FK`) when MoveIt/Servo are off.

### Bottom Dock: Waypoints, Queue & Creator (`QuickActions.vue`, `WaypointCreator.vue`, `RosConsole.vue`)
* **Actions:** `LIGHT` (`/cmd_light`), `Sampling` (`payload:mock_sample`), `▶ RESUME` (`operator:RESUME` + `nav:resume`), `CLEAR` (`system:clear_costmaps`).
* **Queue Mode & Laps:**
  * When `QUEUE: OFF`, clicking a saved point/route sends `nav:go_to_named` with `LAPS` (`1–100`).
  * When `QUEUE: ON`, clicks append entries (`name`, `type`, editable `laps`) to `store.commandQueue`; clicking `▶ RUN QUEUE` dispatches all queued `go_to_named` commands to `waypoint_manager` -> `nav_coordinator` FIFO queue.
  * Each waypoint pill includes a stop-propagated `✖` delete trigger (`waypoints:delete`).
* **Waypoint Creator (`WaypointCreator.vue`):** Saves single `(X, Y, Yaw)` points or accumulates multi-point `[[x, y, yaw], ...]` routes to `waypoints:save` (`tab: 'global'`).

---

## 7. ROS 2 & HTTP Interface Contract

### ROS 2 Topics Subscribed by Web UI 2.0

| Topic | Message Type | Consumer Component / Service | Notes |
|---|---|---|---|
| `/tf`, `/tf_static` | `tf2_msgs/msg/TFMessage` | `SimpleTFClient` | Direct client-side kinematics to `map` |
| `/joint_states` | `sensor_msgs/msg/JointState` | `robotModel.js` (30 Hz), `ArmControl.vue` (10 Hz) | 3D URDF joints + `arm_joint_0..5` sliders |
| `/smart_telemetry` | `smart_interfaces/msg/SmartTelemetry` | `rosConnection.js` | Populates `fsm_state`, speeds, `dose_rate`, `nav_status` |
| `/fsm_status` | `std_msgs/msg/String` | `rosConnection.js` | Overrides/updates `telemetry.fsm_state` |
| `/radiation/status` | `std_msgs/msg/String` (JSON) | `rosConnection.js` | Syncs `{ geiger_active, field_active }` |
| `/waypoints_list` | `std_msgs/msg/String` (JSON) | `rosConnection.js` | Diffed JSON database of saved points & routes |
| `/smart_waypoints_markers` | `visualization_msgs/msg/MarkerArray` | `useWaypoints.js` | 3D cylinder markers + text labels |
| `/map_image/compressed` | `sensor_msgs/msg/CompressedImage` | `useMapLayer.js` | Grayscale PNG + `header.frame_id` metadata string |
| `/radiation_image/compressed` | `sensor_msgs/msg/CompressedImage` | `useRadiationMap.js` | PNG heatmap aligned with map metadata |
| `/plan` | `nav_msgs/msg/Path` | `DigitalTwin3D.vue` | Nav2 global path (orange, `Z+0.02`) |
| `/shadow_path` | `nav_msgs/msg/Path` | `DigitalTwin3D.vue` | Shadow path preview (cyan, `Z+0.03`) |
| `/shadow_marker` | `visualization_msgs/msg/Marker` | `DigitalTwin3D.vue` | Shadow chassis color/alpha/visibility |
| `/camera/image_raw/compressed` | `sensor_msgs/msg/CompressedImage` | `CameraStream.vue` (lazy) | Base64 JPEG stream (RAW mode) |
| `/yolo_overlay/compressed` | `sensor_msgs/msg/CompressedImage` | `CameraStream.vue` (lazy) | Base64 JPEG stream (YOLO mode) |
| `/web_teleop/hub_status` | `std_msgs/msg/String` (JSON) | `ArmControl.vue` | Progress, state, completion for `AUTO` & `GOTO_XYZ` |
| `/web_teleop/tool_pose` | `geometry_msgs/msg/PoseStamped` | `ArmControl.vue` | 5 Hz TCP pose in `arm_base_link` frame |
| `/rosout` | `rcl_interfaces/msg/Log` | `rosConnection.js` -> `RosConsole.vue` | Last 50 log entries |

### ROS 2 Topics & Services Published / Called by Web UI 2.0

| Interface | Type | Direction | Producer |
|---|---|---|---|
| `/robot_state_publisher/get_parameters` | `rcl_interfaces/srv/GetParameters` | Service Call | `robotModel.js` (reads `robot_description`) |
| `/smart_command` | `smart_interfaces/msg/SmartCommand` | Publish | `rosConnection.js` (`pubSmartCommand`) |
| `/cmd_vel`, `/cmd_vel_shadow` | `geometry_msgs/msg/Twist` | Publish (10 Hz) | `teleopCore.js` / `AppHeader.vue` |
| `/cmd_light` | `std_msgs/msg/Bool` | Publish | `QuickActions.vue` |
| `/goal_pose` | `geometry_msgs/msg/PoseStamped` | Publish | `DigitalTwin3D.vue` (2D Nav Goal click/drag) |
| `/web_teleop/cmd_vel` | `geometry_msgs/TwistStamped` | Publish (10 Hz) | `ArmControl.vue` (`arm_base_link` / `arm_tool0`) |
| `/web_teleop/mode` | `std_msgs/String` | Publish | `ArmControl.vue` (`"MANUAL"` / `"AUTO"`) |
| `/web_teleop/hub_request` | `std_msgs/String` (JSON) | Publish | `ArmControl.vue` (`GOTO_XYZ`, `EXECUTE_CSV`, `RESET`) |
| `/web_teleop/unfold`, `/web_teleop/fold` | `std_msgs/Empty` | Publish | `ArmControl.vue` |
| `/arm_controller/joint_trajectory` | `trajectory_msgs/JointTrajectory` | Publish | `ArmControl.vue` (single-point `arm_joint_0..5`) |

> **Type Name Note:** `rosConnection.js` and 3D composables use ROS 2 Jazzy interface strings with `/msg/` (e.g. `geometry_msgs/msg/Twist`), while `ArmControl.vue` uses `sensor_msgs/JointState`, `trajectory_msgs/JointTrajectory`, `geometry_msgs/TwistStamped`, `std_msgs/String`, `std_msgs/Empty`; `rosbridge_suite` resolves both forms on ROS 2.

### `/smart_command` Matrix

| `target_system` | `command` | `payload_json` | Sent From |
|---|---|---|---|
| `system` | `stop`, `start_freeride`, `start:mapping:none`, `start_213`, `start_kitchen`, `start_shelter_zero`, `start:lifelong:<name>`, `save_map:<name>` | `""` | `TeleopTabs.vue` |
| `system` | `clear_costmaps` | `""` | `QuickActions.vue` |
| `system` | `set_speed:<float>` | `""` | `useNavSpeed.js` |
| `system` | `watchdog_on`, `watchdog_off` | `""` | `TeleopTabs.vue` |
| `system` | `rad_on`, `rad_off`, `rad_geiger_on`, `rad_geiger_off`, `rad_record:<file>`, `rad_stop`, `rad_save`, `rad_clear`, `rad_load:<file>` | `""` | `TeleopTabs.vue` |
| `system` | `shadow_on`, `shadow_off` | `""` | `TeleopTabs.vue` |
| `system` | `arm_on`, `arm_off` | `""` | `ArmControl.vue` |
| `nav` | `go_to_named` | `{"name":"...","laps":N}` | `QuickActions.vue`, `NavPopup.vue` |
| `nav` | `cancel` | `{"x":0,"y":0,"yaw":0}` | `AppHeader.vue`, `NavPopup.vue` |
| `nav` | `resume`, `recover_localization` | `""` | `QuickActions.vue`, `NavPopup.vue`, `TeleopTabs.vue` |
| `operator` | `RESUME`, `clear`, `execute` | `""` | `TeleopTabs.vue`, `QuickActions.vue`, `NavPopup.vue` |
| `waypoints` | `save` | `{"name","tab","x","y","yaw"}` or `{"name","tab","points":[[x,y,yaw],...]}` | `WaypointCreator.vue` |
| `waypoints` | `delete` | `{"name":"..."}` | `QuickActions.vue` |
| `payload` | `mock_sample` | `""` | `QuickActions.vue` |

### `smart_server/web_server.py` HTTP Endpoints (`:8080`)

* `/*` -> Serves files from `<ws_root>/src/smart_robotics/Infrastructure_as_Code/web_ui_2.0/dist` (falls back to `index.html` for extensionless client routes, with directory traversal guard).
* `/packages/<pkg>/<path>` -> Resolves via `ament_index_python.get_package_share_directory(pkg)` and enforces `os.path.commonpath` confinement, **strictly allowlisted** in `allowed_pkgs`:
  `ugv_tracked_description`, `manipulator_description`, `smart_master`, `smart_server`, `smart_sim2real`, `smart_moveit_config`. Unlisted packages return `/dev/null` (`404`).
* `/install/<path>`, `/src/<path>` -> Maps to `<ws_root>/install/...` and `<ws_root>/src/...` for legacy URDFs and SDF world assets.
* Response headers inject `Access-Control-Allow-Origin: *` and `Cache-Control: no-store, no-cache, must-revalidate`.

---

## 8. URDF, Mesh & 3D Asset Pipeline

### Loading Sequence
1. On hardware (`use_sim_time:=false`), [`server.launch.py`](../../smart_server/launch/server.launch.py) launches a local `robot_state_publisher` (remapping `/tf -> /tf_server_local` to keep Zenoh radio traffic minimal) and a local `joint_state_publisher` (`source_list: ['/arm_joint_states']`). In simulation, the simulation `robot_state_publisher` serves the parameter directly.
2. `robotModel.js` calls `/robot_state_publisher/get_parameters` (`['robot_description']`) and parses the XML with `urdf-loader`.
3. `urdfLoader.packages` resolves `package://<pkg>/...` URIs to `http://<hostname>:8080/packages/<pkg>/...`. If any third-party URDF still emits absolute `file://.../install/...` paths, `loadMeshCb` intercepts the `/install/` substring and rewrites it to `http://<hostname>:8080/install/...`.
4. `robotModel.js` auto-detects the root link (a link never appearing as a joint child, falling back to `base_footprint`), binds it to `SimpleTFClient`, attaches `THREE.AxesHelper(0.15)` frames to `arm_tool0` (or `arm_gripper_base`) and `arm_base_link`, and links `ArmTrailManager`.

### Asset & Kinematics Rules
1. **Prefer `package://<pkg>/...` in `.urdf.xacro`:** Avoid `file://$(find ...)` so assets resolve identically in Gazebo (`GZ_SIM_RESOURCE_PATH`) and remote browser clients via `/packages/`.
2. **Extend `allowed_pkgs` for new mesh packages:** Any new ROS description package added to the URDF (e.g., sensor packages) must be added to `allowed_pkgs` in [`web_server.py`](../../smart_server/smart_server/web_server.py) or meshes will fail with `404`.
3. **STL Meshes Only:** `robotModel.js` and `useSdfWorlds.js` instantiate only Three.js `STLLoader`. `.dae` (Collada) and `.obj` URIs fail in `loadMeshCb` with `Unsupported mesh format`.
4. **Material Preservation (`keepMaterial`):** STL chassis meshes matching `base.stl` receive `darkBlueMaterial` (`0x1565c0`), arm STL meshes and synchronous URDF geometric primitives receive `lightBlueMaterial` (`0x2196f3`), and `mesh.userData.keepMaterial = true` prevents the synchronous post-parse `urdfRobot.traverse()` pass from overwriting asynchronously loaded STL materials. Meshes/nodes containing `lidar`, `laser`, or `velodyne` are hidden in the 3D view.
5. **Single Manipulator Kinematics Source:** Keep `smart_master/urdf/full_system.urdf.xacro` and `smart_moveit_config/config/smart_robot.urdf.xacro` synchronized. `teleop_manager` extracts the KDL chain directly from `robot_description` between `arm_base_link` and `arm_tool0` to compute `/web_teleop/tool_pose` and weighted DLS IK; any joint offset mismatch skews `AxesHelper`, live telemetry, and `GOTO_XYZ`.

---

## 9. Browser Persistence (`localStorage`)

State persisted client-side is scoped by browser **origin** (`scheme + host + port`, e.g., `http://localhost:8080` vs `http://192.168.x.x:8080` vs `:5173`):

| Key | Written By | Payload / Purpose |
|---|---|---|
| `theme` | `AppHeader.vue` | `'dark'` or `'light'` CAD theme preference |
| `arm_saved_poses` | `ArmControl.vue` | Array of named 6-DOF poses `[{ name, deg: [j0..j5] }]` |
| `arm_active_route` | `ArmControl.vue` | Active `JOINT ROUTE SEQUENCER` step list `[{ id, name, deg, duration, pause }]` |
| `arm_saved_routes` | `ArmControl.vue` | Array of named joint routes `[{ name, steps }]` |

---

## 10. Development, Build & Deployment

### Prerequisites
* Node.js / npm (e.g., via `nvm` in `$HOME/.nvm`) for building or running the dev server
* Running ROS 2 server stack (`rosbridge_websocket` on `:9090` + `smart_server/web_server.py` on `:8080`)

### Development Server (HMR)
```bash
cd src/smart_robotics/Infrastructure_as_Code/web_ui_2.0
npm install
npm run dev
```
* Opens Vite on `http://localhost:5173`.
* **Requirement:** Because `vite.config.js` defines no HTTP proxy, `web_server` (`:8080`) and `rosbridge_websocket` (`:9090`) must already be running in the ROS 2 environment so mesh/SDF requests and WebSocket telemetry succeed.

### Production Build (Required After Editing Vue/JS/CSS)
```bash
cd src/smart_robotics/Infrastructure_as_Code/web_ui_2.0
npm run build
# Or using nvm helper script:
./build_ui.sh
```
* Outputs bundled assets into `web_ui_2.0/dist/`.
* `smart_server/web_server.py` reads directly from `src/smart_robotics/Infrastructure_as_Code/web_ui_2.0/dist` (relative to the resolved workspace root) with `Cache-Control: no-store`. Refreshing the browser picks up UI builds immediately without running `colcon build` for frontend-only changes.
* `node_modules/` is gitignored, while `dist/` is kept in version control so the HMI works out-of-the-box on headless robot/server deployments without requiring Node.js at runtime.

### LAN / Tablet Access
* Open `http://<server-lan-ip>:8080` from a tablet or remote workstation on the same subnet.
* `ConnectionBox.vue` automatically defaults the WebSocket target to `ws://<server-lan-ip>:9090`, and 3D asset loaders target `http://<server-lan-ip>:8080/...`.
* Ports `8080/tcp` (HTTP static & meshes) and `9090/tcp` (`rosbridge_websocket`) must be reachable through the host firewall.

---

## 11. Known Constraints & Technical Debt

| Area | Location in Codebase | Technical Impact |
|---|---|---|
| **Hardcoded CSV Mission Paths** | `ArmControl.vue` (`selectedHubTask`, `<select>` options, `SQUARE_HORIZONTAL_POINTS`, `SQUARE_VERTICAL_POINTS`) | References `/home/oleksandr/ros2_ws/src/manipulator_stack/manipulator_control/manipulator_control/test/square_*.csv` and duplicates preview points in JS; breaks if workspace path or username differs. |
| **Hardcoded `:8080` Asset Origin** | `robotModel.js`, `DigitalTwin3D.vue`, `useSdfWorlds.js` | Constructs `http://${window.location.hostname}:8080/...` directly. Fails when served behind a TLS/non-8080 reverse proxy or via `:5173` without a `:8080` backend (`vite.config.js` lacks `server.proxy`). |
| **Hardcoded Shadow STL & SDF World List** | `DigitalTwin3D.vue` (`base.STL`, initial `loadSDFWorld('213')`, dropdown list), `useSdfWorlds.js` | Assumes `ugv_tracked_description/meshes/base.STL` exists and SDF worlds + STL meshes reside strictly under `smart_sim2real`. |
| **Hardcoded 6-DOF Joint Names & Limits** | `ArmControl.vue` (`jointLimits`, `arm_joint_0..5`) | UI slider ranges (`[-90,90]`, `[-5,180]`, `[-180,5]`, etc.) are not parsed dynamically from `robot_description` or MoveIt `joint_limits.yaml`. |
| **Assumed `map` Fixed Frame** | `DigitalTwin3D.vue` (`SimpleTFClient({ fixedFrame: 'map' })`) | Running manipulator-only setups without SLAM/odom broadcasting `map -> ... -> rootLink` leaves `computeTransform(rootLink)` returning `null`; robot stays at `(0,0,0)`. |
| **Mixed Topic/Thread Handling in Bridge** | `smart_plugins/src/trajectory_bridge.cpp` (duplicated in `manipulator_control`) | Multi-point `JointTrajectory` messages on `/arm_controller/joint_trajectory` spawn detached non-cancelable `sleep_for` threads (worked around cleanly by `JOINTS` sending single-point trajectories; also duplicate bridge sources exist across two packages). |
| **Origin-Bound Persistence** | `ArmControl.vue`, `AppHeader.vue` | Saved arm poses, routes, and theme are stored in browser `localStorage` and do not sync across devices or different hosts/ports. |
| **Single Large JS Bundle Chunk** | `vite.config.js` / `npm run build` | `three`, `roslib`, and `urdf-loader` are bundled into a single chunk without `build.rollupOptions.output.manualChunks` code splitting. |
| **Unused Legacy Files** | `src/components/mechanisms/MechanismsPanel.vue`, `fix-web-ui-haze.patch` | Unimported WIP component and pre-Three.js `ros3d` patch still sit in the repository tree. |
