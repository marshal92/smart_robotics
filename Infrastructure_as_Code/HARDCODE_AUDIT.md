# Infrastructure & Hardcode Audit (`smart_robotics`)

This document tracks environment-specific paths, network addresses, interface names, ports, and hardware assumptions found across `smart_robotics` so they can be replaced step by step without breaking robot or operator-station workflows.

---

## Status Overview

| Step | Scope | Status | Notes |
| --- | --- | --- | --- |
| **Step 1** | Gazebo `.sdf` world mesh URIs (`smart_sim2real/worlds/*.sdf`) | **Completed** | Replaced 80 `file:///home/oleksandr/...` and 2 `model://smart_sim2real/worlds/...` URIs with `package://smart_sim2real/worlds/...`; added `GZ_SIM_RESOURCE_PATH` support in `smart_sim2real/launch/sim.launch.py` and `smart_sim2real/hooks/gz_sim_resource_path.dsv`. |
| **Step 1b** | Legacy `asymmetric_radiation_*` package deps (`smart_nav/package.xml`, `smart_master/package.xml`) | **Completed** | Removed stale `asymmetric_radiation_plugins` and replaced `asymmetric_radiation_core` with `smart_radiation`. |
| **Group B** | Username (`/home/oleksandr`) & workspace layout (`~/ros2_ws/src/smart_robotics`) | **Partial** | `CYCLONEDDS_URI` now falls back dynamically (`os.environ` / `$HOME/cyclonedds.xml` / inline XML) in `start_robot.sh`, `start_server.sh`, `mission_manager.py`, and `twin_orchestrator.py`; remaining workspace/map paths tracked below. |
| **Group C** | Network IPs, NIC names, HTTP/WS ports, udev device paths | **Pending** | Tracked below; parameterize via `.env` / launch config and udev deployment rules. |

---

## Group B — Hardcoded Username & Workspace Paths

| Component / File | Lines | Hardcoded Value | Risk / Impact | Proposed Fix |
| --- | --- | --- | --- | --- |
| `smart_control/smart_control/mission_manager.py` | 83 | `source ~/ros2_ws/install/setup.bash` in spawned tmux command (`CYCLONEDDS_URI` already uses `env -> ~/cyclonedds.xml -> inline` fallback at 77–80) | Fails if workspace is not `~/ros2_ws` | Derive setup script from `COLCON_PREFIX_PATH` / `SMART_WS_ROOT` or inherit current env |
| `smart_control/smart_control/mission_manager.py` | 312 | `~/ros2_ws/src/smart_robotics/smart_nav/maps/{map_name}` | Map saving/loading fails if repo path differs | Use a configurable parameter / `SMART_NAV_MAPS_DIR` env var + runtime dir (`~/.local/share/smart_robotics/nav_maps`) |
| `smart_control/smart_control/recovery_relocalizer.py` | 42 | `'/home/oleksandr/ros2_ws/src/smart_robotics/smart_nav/maps'` | Relocalization fails to locate maps on another user/path | Resolve `smart_nav/maps` dynamically via ROS package share + optional workspace override |
| `smart_server/smart_server/twin_orchestrator.py` | 73 | `source ~/ros2_ws/install/setup.bash` (`CYCLONEDDS_URI` fallback at 67–70) | Fails if workspace is not `~/ros2_ws` | Inherit current environment or derive setup script from `COLCON_PREFIX_PATH` / env var |
| `smart_server/smart_server/web_server.py` | 164–166 | `os.path.join(share_dir, '..', '..', '..', '..')` + `src/smart_robotics/Infrastructure_as_Code/web_ui_2.0/dist` | Assumes merged/isolated colcon layout 4 levels below `smart_server/share` | Use env override (e.g. `SMART_WEB_DIST_DIR`), resolve symlinked source / installed asset, and serve via `ament_index` package lookup |
| `smart_radiation_plugins/src/virtual_geiger_node.cpp` | 130 | `(home ? home : "/home/oleksandr") + "/ros2_ws/src/smart_robotics/smart_radiation/maps"` | Fallback breaks when workspace is not `~/ros2_ws` | Prefer `SMART_RADIATION_MAPS_DIR` or `ament_index_cpp::get_package_share_directory("smart_radiation") + "/maps"` |
| `smart_radiation_plugins/src/radiation_mapper_node.cpp` | 221 | `(home ? home : "/home/oleksandr") + "/ros2_ws/src/smart_robotics/smart_radiation/maps"` | Same workspace layout assumption | Same fix as `virtual_geiger_node.cpp` |
| `smart_radiation/launch/radiation_bringup.launch.py` | 19, 29 | `Path.home() / 'ros2_ws' / 'src' / 'smart_robotics' / 'smart_radiation' / ...` (`ws_maps`, `ws_cfg`) | `ws_cfg` / `ws_maps` checks `~/ros2_ws` before `get_package_share_directory('smart_radiation')` | Use `get_package_share_directory('smart_radiation')` or `Path(__file__).resolve().parent.parent` first (plus env override) so installed/relocated workspaces always match active build |
| `smart_sandbox/smart_sandbox/block2a_logger.py`<br>`smart_sandbox/smart_sandbox/block2b_logger.py`<br>`smart_sandbox/smart_sandbox/block4_logger.py` | 60<br>74<br>101 | `'/home/oleksandr/ros2_ws/src/smart_robotics/smart_sandbox/logs'` | Experiment loggers fail on another user/path | Default to `Path.home() / '.ros' / 'smart_sandbox_logs'` or env/parameter |
| `Infrastructure_as_Code/web_ui_2.0/src/components/teleop/arm/ArmAutoTab.vue` | 18, 21, 158 | `/home/oleksandr/ros2_ws/src/manipulator_stack/manipulator_control/manipulator_control/test/square_{horizontal,vertical}.csv` | Preset trajectory missions fail if username/workspace path differs | Pass relative preset names or `package://manipulator_control/...` resolved by backend node |
| `Infrastructure_as_Code/autostart/smart_launcher.py` | 65, 69–72, 79, 484 | `ROBOT_USER = "oleksandr"`, `~/ros2_ws/src/smart_robotics/...`, `source ~/ros2_ws/install/setup.bash` | Launcher only works for user `oleksandr` and `~/ros2_ws` | Move user/IP/workspace root into a config file or CLI/env defaults (`$USER`, repo-relative `Path(__file__)`) |
| `Infrastructure_as_Code/autostart/start_robot.sh` | 56 | `source ~/ros2_ws/install/setup.bash` (`CYCLONEDDS_URI` already uses `${CYCLONEDDS_URI:-file://$HOME/cyclonedds.xml}` + inline XML fallback at 7–13) | Assumes workspace is `~/ros2_ws` | Resolve workspace root relative to script path (`SCRIPT_DIR/../../../..`) |
| `Infrastructure_as_Code/autostart/start_server.sh` | 58 | `source ~/ros2_ws/install/setup.bash` (`CYCLONEDDS_URI` already uses `${CYCLONEDDS_URI:-file://$HOME/cyclonedds.xml}` + inline XML fallback at 8–14) | Assumes `~/ros2_ws` | Resolve workspace root relative to script path (`SCRIPT_DIR/../../../..`) |
| Host `~/.bashrc` | 119, 123 | `source ~/ros2_ws/install/setup.bash`, `GZ_SIM_RESOURCE_PATH` appending `~/ros2_ws/install/fcm_digital_twin/share` | Workstation-only shell assumption | Keep local convenience aliases out of package requirements |

---

## Group C — Network, Interface, Port & Device Hardcodes

| Component / File | Lines | Hardcoded Value | Risk / Impact | Proposed Fix |
| --- | --- | --- | --- | --- |
| `Infrastructure_as_Code/autostart/start_server.sh`<br>`Infrastructure_as_Code/autostart/smart_launcher.py`<br>`Infrastructure_as_Code/configs/cyclonedds_server.xml` | 4<br>66<br>15 | `192.168.31.100` (robot static IP) | Breaks whenever router subnet / robot DHCP lease / VPN changes | Factor into shared env/config (`.env` or mDNS/Tailscale hostname such as parameterizable `SMART_ROBOT_IP`) |
| `Infrastructure_as_Code/configs/cyclonedds.xml`<br>`Infrastructure_as_Code/configs/cyclonedds_server.xml` | 6<br>7 | `ros0` (robot NIC), `wlp82s0` (operator laptop Wi-Fi NIC) | CycloneDDS fails to start if Wi-Fi/Ethernet interface name differs on another host | Generate CycloneDDS XML from template / env var or auto-detect active interface |
| `Infrastructure_as_Code/autostart/smart_launcher.py`<br>`smart_server/smart_server/web_server.py`<br>`Infrastructure_as_Code/web_ui_2.0/src/components/layout/ConnectionBox.vue`<br>`Infrastructure_as_Code/web_ui_2.0/src/components/layout/DigitalTwin3D.vue`<br>`Infrastructure_as_Code/web_ui_2.0/src/components/layout/composables/useSdfWorlds.js`<br>`Infrastructure_as_Code/web_ui_2.0/src/three/robotModel.js` | 75–76<br>161<br>43<br>491, 507<br>32, 95<br>69, 101–103 | Fixed HTTP port `8080` and `rosbridge` WebSocket port `9090`, plus `/install/<pkg>/share/<pkg>/...` HTTP paths & Shadow `base.STL` | Port collisions or reverse-proxy / Vite dev port mismatch (`window.location.hostname:8080`) | Use `window.location.origin` (or configurable URL/port via Vite env / query / config JSON) in Web UI, and derive paths from `/packages/<pkg>/...` consistently |
| `Infrastructure_as_Code/autostart/start_robot.sh`<br>`smart_radiation/smart_radiation/accurad_protocol.py` | 51–52<br>14 | `/dev/esp32s3`, `/dev/accurad` | Requires matching `/etc/udev/rules.d/` entries on **both** laptop and Raspberry Pi (`99-linorobot.rules` etc.) | Store versioned udev rules template under `Infrastructure_as_Code/configs/` with clear serial/VID:PID setup instructions; keep ROS params (`port`) overridable |
| `Infrastructure_as_Code/autostart/start_robot.sh`<br>`Infrastructure_as_Code/autostart/start_server.sh` | 16–43 (robot)<br>21–49 (server) | Zenoh DDS bridge `--allow` regex list (`^rt/smart_telemetry$`, `^rt/radiation_map$`, `^rt/radiation_image/compressed$`, `^rt/radiation/status$`, etc.) | Intentional bandwidth filter, but easy to drift between robot and server scripts when adding/renaming topics | Centralize allowlist in a shared config/file read by both scripts; keep `/radiation/dose` local on robot unless cross-host debugging or split-host sensor placement is needed |

---

## Recommended Next Steps Order

1. **Completed:** `smart_sim2real/worlds/*.sdf` mesh URI portability + `sim.launch.py` / ament hook `GZ_SIM_RESOURCE_PATH`.
2. **Completed:** Removed legacy `asymmetric_radiation_*` `<exec_depend>` entries from `smart_nav/package.xml` and `smart_master/package.xml`.
3. **Next (after CycloneDDS / real hardware check):** Versioned udev rules template in `Infrastructure_as_Code/configs/` + execute the 3-step map/config path migration plan below (`smart_nav`, `smart_control`, `smart_radiation`, `smart_radiation_plugins`, plus `ArmAutoTab.vue` / `web_server.py`).
4. **Finally:** Centralize network configuration (`ROBOT_IP`, NIC names, Zenoh allowlist / `rmw_zenohd` ACL, HTTP/WS ports) and `CYCLONEDDS_URI` / `mission_manager.py` / `twin_orchestrator.py` workspace resolution in `Infrastructure_as_Code/`.

---

## Planned 3-Step Migration for Map & Config Paths (Group B)

### Why a single `FindPackageShare('.../maps')` replacement is not enough
* **`smart_nav` (`ament_cmake` with `--symlink-install`):** `install/smart_nav/share/smart_nav/maps/` is a real directory containing per-file symlinks generated only at `colcon build` time (`213_map.*`, `kitchen_map.*`, `shelter_*`). A new map saved at runtime by `mission_manager.py` would either miss `install/share` until rebuild or risk overwriting/orphaning build artifacts.
* **`smart_radiation` (`ament_python` with `--symlink-install`):** `install/smart_radiation/share/smart_radiation/maps/*` symlinks point into `build/smart_radiation/maps/*`. Writing new runtime `.npy`/`.csv` outputs into `build/` or `install/share/` means `rm -rf build install` would wipe recorded radiation runs.
* **Clean split:** Separate **writable runtime maps** (default persistent user dir or `SMART_*_MAPS_DIR`) from **read-only bundled package maps** (`share/<pkg>/maps` fallback).

### Step 1 — Navigation Maps (`smart_control` + `smart_nav`)
* **Save path (`smart_control/smart_control/mission_manager.py` -> `_native_save_map`):**
  1. Explicit `maps_dir` ROS parameter (if non-empty)
  2. `SMART_NAV_MAPS_DIR` environment variable (optional override if developer wants to write directly to source repo)
  3. Default persistent runtime dir: `~/.local/share/smart_robotics/nav_maps` (auto-created with `os.makedirs(..., exist_ok=True)`).
* **Load / lookup path (`recovery_relocalizer.py`, `smart_nav/launch/slam_lifelong.launch.py`, `smart_nav/launch/slam_mapping.launch.py`):**
  1. `maps_dir` param / `SMART_NAV_MAPS_DIR` (if requested map exists there)
  2. `~/.local/share/smart_robotics/nav_maps` (newly saved maps are immediately usable without re-running `colcon build`)
  3. Fallback: `get_package_share_directory('smart_nav') / 'maps'` (bundled baseline maps like `213_map`, `kitchen_map`, `shelter_*`).
* **Verification:** Launch `slam_lifelong` & `recovery_relocalizer` on bundled `213_map`; save a test map via `mission_manager` (`save_map test_map`) and reload it without rebuilding.

### Step 2 — Radiation Launch & Python Precedence (`smart_radiation`)
* **`smart_radiation/launch/radiation_bringup.launch.py`:**
  * In `_default_params_file()`, stop checking `Path.home() / 'ros2_ws' / ...` before `get_package_share_directory('smart_radiation')`; order should be `SMART_RADIATION_PARAMS_FILE` (optional env override) -> `get_package_share_directory('smart_radiation') / 'config' / 'radiation_params.yaml'`.
  * In `_default_maps_dir()`, drop the hardcoded `Path.home() / 'ros2_ws' / ...` branch and align resolution across `radiation_field_server.py`, `radiation_manager.py`, and `baseline_field_server.py` (`SMART_RADIATION_MAPS_DIR` -> runtime dir for writable maps -> `share/smart_radiation/maps` fallback for pre-generated reference `.npy` maps).
* **Verification:** Run `ros2 launch smart_radiation radiation_bringup.launch.py --show-args` and test with overridden `HOME` to confirm the active sourced workspace config/maps are selected.

### Step 3 — C++ Fallbacks (`smart_radiation_plugins`)
* **`virtual_geiger_node.cpp` (`load_truth_map`) & `radiation_mapper_node.cpp` (`resolve_paths`):**
  * Replace `(home ? home : "/home/oleksandr") + "/ros2_ws/src/smart_robotics/smart_radiation/maps"` with a single shared header helper (no duplicated logic):
    1. Non-empty `maps_dir` parameter (preserved when launched via `radiation_bringup.launch.py`)
    2. `SMART_RADIATION_MAPS_DIR` environment variable
    3. Read fallback (`virtual_geiger_node`): `ament_index_cpp::get_package_share_directory("smart_radiation") + "/maps"` (add `ament_index_cpp` to `smart_radiation_plugins/package.xml` & `CMakeLists.txt`; `ros-jazzy-ament-index-cpp` is already installed); Write fallback (`radiation_mapper_node`): `~/.local/share/smart_robotics/rad_maps` with `std::filesystem::create_directories`.
* **Verification:** `colcon build --packages-select smart_radiation_plugins` and direct `ros2 run` invocation of both nodes without passing `maps_dir`.
