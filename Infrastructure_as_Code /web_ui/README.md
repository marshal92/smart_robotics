# Smart Robotics Web UI

This repository contains the web interface for controlling and monitoring Smart Robotics systems. It is a modern Single Page Application (SPA) designed for full telemetry visualization and teleoperation of the mobile robot (UGV) and its subsystems.

## Technology Stack
*   **Framework:** [Vue 3](https://vuejs.org/) (Composition API, `<script setup>`)
*   **Bundler:** [Vite](https://vitejs.dev/) (Lightning-fast HMR and building)
*   **State Management:** [Pinia](https://pinia.vuejs.org/) (Centralized ROS data store)
*   **ROS Integration:** [roslibjs](https://github.com/RobotWebTools/roslibjs) (WebSocket communication with `rosbridge_server`)
*   **3D Visualization:** [ros3djs](https://github.com/RobotWebTools/ros3djs) built on top of `three.js` (Digital Twin)

---

## Project Structure (File Tree)

```text
web_ui/
├── index.html                  # Main entry point for Vue
├── package.json                # Dependencies (Vue, Pinia, roslib, three)
├── vite.config.js              # Vite bundler configuration
├── public/                     # Static assets (icons, meshes if needed)
└── src/
    ├── main.js                 # App initialization (Vue + Pinia)
    ├── App.vue                 # Root component (handles ROS connection logic)
    ├── assets/
    │   └── index.css           # Global styles, CSS variables, dark theme
    ├── services/
    │   └── rosConnection.js    # Singleton/wrapper for ROS WebSocket connection
    ├── stores/
    │   └── rosStore.js         # Pinia store holding live telemetry and state
    └── components/
        ├── layout/             # Core layout elements (HUD, 3D scene)
        │   ├── DigitalTwin3D.vue
        │   └── TelemetryHUD.vue
        ├── mission/            # Mission & mapping tools
        │   ├── MissionManager.vue
        │   └── WaypointCreator.vue
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
   * `fsm_state` (String) — Current Finite State Machine status (NORMAL, COLLISION, etc.).
   * `nav_status` (String) — Navigator status (IDLE, MOVING).
   * `linear_speed`, `angular_speed` (Float32) — Current velocities.
   * `dose_rate` (Float32) — Current radiation level.
   * `light_is_on` (Bool) — Illumination status.

2. **`/smart_command`** (`smart_interfaces/msg/SmartCommand`) — Data **TO** the robot.
   * `target_system` (String) — Destination system (`nav`, `payload`, `system`, `operator`).
   * `command` (String) — The command itself (`go_to`, `stop`, `clear_costmaps`, `save_map`).
   * `payload_json` (String) — Additional JSON parameters (e.g., X, Y coordinates).

### Standard Topics
*   `/tf` — Transforms for the 3D model.
*   `/map` — Global SLAM map.
*   `/local_costmap/costmap` — Local obstacle map.
*   `/plan` — Nav2 planned path.
*   `/image_raw/compressed` — Live camera feed (MJPEG).
*   `/radiation_image/compressed` — Radiation field heat map (compressed image).

---

## Architecture and Backend Support

The web interface relies on several specialized Python nodes from the `smart_server` and `smart_radiation` packages to function correctly:

### 1. Backend Nodes (`smart_server` & `smart_radiation`)
*   **`web_server.py` (`smart_server`)**: Acts as the primary HTTP server. It serves the built static files (from the `dist` folder), parses the simulation world, and loads 3D models for the interface.
*   **`map_to_image.py` (`smart_server`)**: A utility node responsible for rendering the SLAM map into an image format easily digestible by the web UI.
*   **`radiation_field_server.py` (`smart_radiation`)**: Modified to process the radiation field data and stream it as a compressed image via the `/radiation_image/compressed` topic, avoiding heavy PointCloud rendering in the browser.

### 2. Communication Layer (`src/services/rosConnection.js`)
The single entry point for `rosbridge_server` communication.
*   Establishes a WebSocket connection (defaults to `ws://localhost:9090`).
*   Provides ready-to-use publishing functions:
    *   `pubTwist()` — For the virtual joystick (`/cmd_vel`).
    *   `pubSmartCommand()` — The core system! Sends tactical commands to `/smart_command`.

### 3. State Layer (`src/stores/rosStore.js`)
The Pinia store acts as the "brain" of the frontend.
*   Subscribes to telemetry topics.
*   Reactively updates variables. Any Vue component simply reads from `rosStore` without worrying about network logic, ensuring UI synchronization.

---

## Interface Breakdown (Components)

The interface is visually divided into 3 main layers:

### 1. Digital Twin (`layout/DigitalTwin3D.vue`)
The 3D scene that mirrors exactly what the robot "sees" and "thinks" in real-time:
*   **Environment:** Loads the global map (`/map`) and overlays local obstacles (`/local_costmap/costmap`).
*   **Robot:** Renders the 3D STL model and rotates it based on ROS transforms (`/tf`). (Can be easily swapped to `ROS3D.UrdfClient` for manipulators).
*   **Radiation:** Displays the invisible radiation field from `/radiation_image/compressed`.
*   **Navigation Tools:** Allows click-and-drag navigation (Nav Goal button) drawing arrows directly on the 3D floor, and visualizes the planned path (`/plan`).

### 2. Telemetry HUD (`layout/TelemetryHUD.vue`)
Displays critical parameters in real-time: FSM state, linear speed, radiation level, and connection status. Colors dynamically change based on threat levels (e.g., turns orange/red on high radiation).

### 3. Side Control Panel (`teleop/`)
Tab-based layout for different operational scenarios:
*   **Mission Manager:** Controls the robot's "long-term memory" (Lifelong SLAM). Buttons to save and load maps. Security system management (Watchdog ON/OFF).
*   **Direct Teleop:** Manual control featuring a virtual on-screen joystick (`nipple.js`) and payload controls (e.g., dropping cargo, toggling lights).
*   **Shadow Control:** Tactical module. Hands over control to the server for waypoint-based autonomous missions.
*   **Camera Stream:** Pop-up window for live camera feeds (supports click-to-fullscreen).

---

## Styling and Design (CSS)
Built using **Vanilla CSS** without frameworks like Tailwind for 100% design control.
Global variables are defined in `index.css`:
*   Workflow colors: `#10b981` (Success/Moving), `#ef4444` (Error/Stopped), `#f59e0b` (Warning/Radiation).
*   Button backgrounds: Sleek dark gray (`#555`) with bright bottom borders for accent.
*   Glassmorphism effects (`backdrop-filter: blur()`) are applied to panels overlaying the 3D scene.

---

## Running and Building

### Development (Dev Server)
To edit the UI code and see changes instantly in the browser without rebuilding ROS packages (Hot Reload):
```bash
cd src/smart_robotics/Infrastructure_as_Code\ /web_ui
npm install
npm run dev
```
*(The site will be hosted at `http://localhost:5173`. Make sure `rosbridge_server` is running).*

### Production Build
For the ROS server (`web_server.py`) to serve the site, it must be compiled into static minified HTML/JS/CSS:
```bash
cd src/smart_robotics/Infrastructure_as_Code\ /web_ui
npm run build
```
This command minifies the code and places it in the `dist` folder.
The Python node `web_server.py` reads exactly this `dist` folder and hosts it at `http://localhost:8080`.

> **Note:** The `node_modules` folder is strictly ignored by Git as it is very large. The `dist` folder is included in the index so that other team members can launch the web interface immediately after cloning the repository without needing to install `npm` or build it themselves.
