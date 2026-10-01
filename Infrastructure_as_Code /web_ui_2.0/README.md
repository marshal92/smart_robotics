# Smart Robotics Web UI 2.0 (High-Performance Edition)

This repository contains the web interface for controlling and monitoring Smart Robotics systems. It is a modern Single Page Application (SPA) designed for full telemetry visualization and teleoperation of the mobile robot (UGV) and its subsystems.

**Version 2.0 brings a massive architectural overhaul**, replacing legacy ROS web libraries with highly optimized, low-level implementations for maximum performance and zero memory leaks.

## Technology Stack & Architectural Shifts
*   **Framework:** [Vue 3](https://vuejs.org/) (Composition API, `<script setup>`)
*   **Bundler:** [Vite](https://vitejs.dev/) (Lightning-fast HMR and building)
*   **State Management:** [Pinia](https://pinia.vuejs.org/) (Centralized ROS data store)
*   **ROS Integration:** [roslibjs](https://github.com/RobotWebTools/roslibjs) (WebSocket communication with `rosbridge_server`)
*   **3D Visualization (NEW):** Native [three.js](https://threejs.org/) combined with [urdf-loader](https://github.com/gkjohnson/urdf-loaders).
    *   *Why?* We completely **removed `ros3djs`** due to its heavy abstractions and performance limitations. Using raw `three.js` gives us 100% control over the render loop, lighting, shadows, and memory management.
*   **TF Client (NEW):** Custom `SimpleTFClient.js`.
    *   *Why?* We **removed `tf2_web_republisher`** from the backend. The new `SimpleTFClient` subscribes directly to `/tf` and `/tf_static` via WebSocket and computes transformation matrices directly in the browser. 

## Major Optimizations & Features in 2.0

### 1. Zero Memory Leak TF Processing
The `/tf` topic runs at 50Hz+, which historically crashed browsers due to Garbage Collection (GC) pauses when creating thousands of `THREE.Matrix4` or `THREE.Vector3` objects per second.
Our custom `SimpleTFClient` completely eliminates GC overhead by:
*   **Pre-allocating memory:** Instantiating math objects (`_pos`, `_rot`) once in the constructor.
*   **Decoupling from ROS (requestAnimationFrame):** The TF math and callback execution are now decoupled from the WebSocket message rate. Calculations only happen when the monitor is actually ready to draw a new frame (e.g., 60 FPS), even if ROS sends messages at 100Hz.

### 2. High-Performance Sensor Rendering
*   **Maps & Radiation:** Instead of streaming heavy PointCloud2 data or OccupancyGrids directly to the browser, the backend (`smart_server` and `smart_radiation`) compresses these fields into colored PNGs. The Web UI subscribes to `sensor_msgs/msg/CompressedImage` and projects them instantly onto 3D planes as textures. This allows for 4K-resolution maps with almost zero CPU footprint.

### 3. Dynamic URDF Loading
The UI no longer relies on hardcoded STL meshes for the robot base. It uses `urdf-loader` to dynamically download the XML string from `/robot_description`, parse the kinematic tree, and load all associated `.STL` visuals. It then subscribes directly to `/joint_states` to animate components (like the manipulator arm) in real-time natively in Three.js.

---

## Project Structure (File Tree)

```text
web_ui_2.0/
├── index.html                  # Main entry point for Vue
├── package.json                # Dependencies (Vue, Pinia, roslib, three, urdf-loader)
├── vite.config.js              # Vite bundler configuration
└── src/
    ├── main.js                 # App initialization (Vue + Pinia)
    ├── App.vue                 # Root component (handles ROS connection logic)
    ├── assets/
    │   └── index.css           # Global styles, Premium UI tokens, glassmorphism
    ├── services/
    │   ├── rosConnection.js    # Singleton/wrapper for ROS WebSocket connection
    │   └── simpleTfClient.js   # Custom, GC-optimized TF computation engine
    ├── three/
    │   ├── createViewer.js     # Three.js scene, lighting, and camera setup
    │   └── robotModel.js       # urdf-loader implementation & joint_state syncing
    ├── stores/
    │   └── rosStore.js         # Pinia store holding live telemetry and state
    └── components/
        ├── layout/             # Core layout elements (HUD, 3D scene)
        │   ├── DigitalTwin3D.vue
        │   └── TelemetryHUD.vue
        └── teleop/             # Direct control modules
            ├── CameraStream.vue
            ├── QuickActions.vue
            └── TeleopTabs.vue
```

---

## ROS Integration: Topics and Messages

### Core Custom Messages (`smart_interfaces`)
The UI communicates with the robot via **two primary custom messages**, keeping the architecture clean:

1. **`/smart_telemetry`** (`smart_interfaces/msg/SmartTelemetry`) — Data **FROM** the robot.
   * `fsm_state`, `nav_status` (String) — System states.
   * `linear_speed`, `angular_speed`, `dose_rate` (Float32) — Telemetry.
   * `light_is_on` (Bool) — Subsystem toggles.

2. **`/smart_command`** (`smart_interfaces/msg/SmartCommand`) — Data **TO** the robot.
   * `target_system` (String) — Destination system (`nav`, `payload`, `system`, `operator`).
   * `command` (String) — Command type (`go_to`, `stop`, `clear_costmaps`, `save_map`).
   * `payload_json` (String) — Arguments (e.g., coordinates).

### Standard Topics
*   `/tf` & `/tf_static` — Spatial transforms (computed client-side).
*   `/joint_states` — Real-time manipulator and wheel articulation.
*   `/map_image/compressed` — 2D SLAM map (Optimized).
*   `/radiation_image/compressed` — Radiation heatmap (Optimized).
*   `/image_raw/compressed` — Live camera feed (MJPEG).

---

## Interface Breakdown (Components)

### 1. Digital Twin (`layout/DigitalTwin3D.vue`)
The 3D scene that mirrors exactly what the robot "sees" and "thinks" in real-time.
*   **Environment:** Renders image-projected maps and radiation fields.
*   **URDF Robot:** Accurately articulates all joints based on `/joint_states`.
*   **Navigation Tools:** Custom Raycaster implementation allowing the operator to click directly on the 3D floor. Draws dynamic 3D arrows from the robot to the goal to command Nav2 without standard RViz tools.

### 2. Telemetry HUD (`layout/TelemetryHUD.vue`)
Displays critical parameters in real-time: FSM state, linear speed, radiation level, and connection status. Colors dynamically change based on threat levels (e.g., turns orange/red on high radiation).

### 3. Side Control Panel (`teleop/`)
Tab-based layout for different operational scenarios:
*   **Mission Manager:** Controls the robot's "long-term memory" (Lifelong SLAM). Buttons to save and load maps. Security system management (Watchdog ON/OFF).
*   **Direct Teleop:** Manual control featuring a virtual on-screen joystick (`nipple.js`).

---

## Styling and Design (CSS)
Built using **Vanilla CSS** without frameworks for 100% design control, achieving a premium, sci-fi aesthetic.
*   **Aesthetics:** High use of vibrant accents, dark mode backgrounds (`#1e1e2f`), and glassmorphism panels (`backdrop-filter: blur(12px)`) layered over the 3D canvas.
*   **Workflow Colors:** `#00ffcc` (Neon Cyan/Success), `#ff003c` (Neon Red/Error), `#ff9900` (Warning/Radiation).
*   **Micro-animations:** Smooth transitions on hover states, pulsing indicators for live data streams, and dynamic glow effects to make the interface feel alive and highly responsive.

---

## Running and Building

### Development (Dev Server)
To edit the UI code and see changes instantly in the browser without rebuilding ROS packages (Hot Reload):
```bash
cd src/smart_robotics/Infrastructure_as_Code\ /web_ui_2.0
npm install
npm run dev
```
*(The site will be hosted at `http://localhost:5173`. Make sure `rosbridge_server` is running).*

### Production Build
For the ROS server (`web_server.py`) to serve the site, it must be compiled into static minified HTML/JS/CSS:
```bash
cd src/smart_robotics/Infrastructure_as_Code\ /web_ui_2.0
npm run build
```
This command minifies the code and places it in the `dist` folder.
The Python node `web_server.py` reads exactly this `dist` folder and hosts it at `http://localhost:8080`.

> **Note:** The `node_modules` folder is strictly ignored by Git. The `dist` folder is included in the index so that other team members can launch the web interface immediately after cloning the repository without needing to install `npm` or build it themselves.
