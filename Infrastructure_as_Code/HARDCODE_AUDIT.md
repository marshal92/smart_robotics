# Infrastructure & Hardcode Audit (`smart_robotics`)

This document tracks environment-specific paths, network addresses, interface names, ports, and hardware assumptions found across `smart_robotics` so they can be replaced step by step without breaking robot or operator-station workflows.

---

## Status Overview

| Step | Scope | Status | Notes |
| --- | --- | --- | --- |
| **Step 1** | Gazebo `.sdf` world mesh URIs (`smart_sim2real/worlds/*.sdf`) | **Completed** | Replaced 80 `file:///home/oleksandr/...` and 2 `model://smart_sim2real/worlds/...` URIs with `package://smart_sim2real/worlds/...`; added `GZ_SIM_RESOURCE_PATH` support in `smart_sim2real/launch/sim.launch.py` and `smart_sim2real/hooks/gz_sim_resource_path.dsv`. |
| **Group B** | Username (`/home/oleksandr`) & workspace layout (`~/ros2_ws/src/smart_robotics`) | **Pending** | Tracked below; fix incrementally using ROS 2 package share (`ament_index`), env vars (`SMART_WS_ROOT`, `CYCLONEDDS_URI`), and launch arguments. |
| **Group C** | Network IPs, NIC names, HTTP/WS ports, udev device paths | **Pending** | Tracked below; parameterize via `.env` / launch config and udev deployment rules. |

---

## Group B — Hardcoded Username & Workspace Paths

| Component / File | Lines | Hardcoded Value | Risk / Impact | Proposed Fix |
| --- | --- | --- | --- | --- |
| `smart_control/smart_control/mission_manager.py` | 70–72 | `source ~/ros2_ws/install/setup.bash` and `/home/oleksandr/cyclonedds.xml` in spawned radiation subprocess | Fails on any other user or workspace path; silently drops CycloneDDS config outside `/home/oleksandr` | Inherit current process ROS 2 env (`os.environ`) or resolve workspace setup/config via env vars instead of hardcoded shell string |
| `smart_control/smart_control/mission_manager.py` | 294 | `/home/oleksandr/ros2_ws/src/smart_robotics/smart_nav/maps/{map_name}` | Map saving/loading fails if repo or user differs | Use a configurable parameter / `SMART_NAV_MAPS_DIR` env var or `ament_index` source-or-share resolver |
| `smart_control/smart_control/recovery_relocalizer.py` | 42 | `'/home/oleksandr/ros2_ws/src/smart_robotics/smart_nav/maps'` | Relocalization fails to locate maps on another user/path | Resolve `smart_nav/maps` dynamically via ROS package share + optional workspace override |
| `smart_server/smart_server/twin_orchestrator.py` | 60 | `source ~/ros2_ws/install/setup.bash` | Fails if workspace is not `~/ros2_ws` | Inherit current environment or derive setup script from `COLCON_PREFIX_PATH` / env var |
| `smart_server/smart_server/web_server.py` | 164–166 | `os.path.join(share_dir, '..', '..', '..', '..')` + `src/smart_robotics/Infrastructure_as_Code/web_ui_2.0/dist` | Assumes merged/isolated colcon layout 4 levels below `smart_server/share` | Use env override (e.g. `SMART_WEB_DIST_DIR`), resolve symlinked source / installed asset, and serve via `ament_index` package lookup |
| `smart_radiation_plugins/src/virtual_geiger_node.cpp` | 130 | `(home ? home : "/home/oleksandr") + "/ros2_ws/src/smart_robotics/smart_radiation/maps"` | Fallback breaks when workspace is not `~/ros2_ws` | Prefer `SMART_RADIATION_MAPS_DIR` or `ament_index_cpp::get_package_share_directory("smart_radiation") + "/maps"` |
| `smart_radiation_plugins/src/radiation_mapper_node.cpp` | 221 | `(home ? home : "/home/oleksandr") + "/ros2_ws/src/smart_robotics/smart_radiation/maps"` | Same workspace layout assumption | Same fix as `virtual_geiger_node.cpp` |
| `smart_radiation/launch/radiation_bringup.launch.py` | 19, 29 | `Path.home() / 'ros2_ws' / 'src' / 'smart_robotics' / 'smart_radiation' / ...` (`ws_maps`, `ws_cfg`) | `ws_cfg` / `ws_maps` checks `~/ros2_ws` before `get_package_share_directory('smart_radiation')` | Use `get_package_share_directory('smart_radiation')` or `Path(__file__).resolve().parent.parent` first (plus env override) so installed/relocated workspaces always match active build |
| `smart_sandbox/smart_sandbox/block2a_logger.py`<br>`smart_sandbox/smart_sandbox/block2b_logger.py`<br>`smart_sandbox/smart_sandbox/block4_logger.py` | 60<br>74<br>101 | `'/home/oleksandr/ros2_ws/src/smart_robotics/smart_sandbox/logs'` | Experiment loggers fail on another user/path | Default to `Path.home() / '.ros' / 'smart_sandbox_logs'` or env/parameter |
| `Infrastructure_as_Code/web_ui_2.0/src/components/teleop/arm/ArmAutoTab.vue` | 18, 21, 158 | `/home/oleksandr/ros2_ws/src/manipulator_stack/manipulator_control/manipulator_control/test/square_{horizontal,vertical}.csv` | Preset trajectory missions fail if username/workspace path differs | Pass relative preset names or `package://manipulator_control/...` resolved by backend node |
| `Infrastructure_as_Code/autostart/smart_launcher.py` | 57, 61–63, 71, 434 | `ROBOT_USER = "oleksandr"`, `~/ros2_ws/src/smart_robotics/...`, `source ~/ros2_ws/install/setup.bash` | Launcher only works for user `oleksandr` and `~/ros2_ws` | Move user/IP/workspace root into a config file or CLI/env defaults (`$USER`, repo-relative `Path(__file__)`) |
| `Infrastructure_as_Code/autostart/start_robot.sh` | 7, 50 | `CYCLONEDDS_URI=file:///home/oleksandr/cyclonedds.xml`, `source ~/ros2_ws/install/setup.bash` | Assumes script runs as `oleksandr` and workspace is `~/ros2_ws` | Use `${CYCLONEDDS_URI:-file://$HOME/cyclonedds.xml}` and script-relative workspace discovery |
| `Infrastructure_as_Code/autostart/start_server.sh` | 48 | `source ~/ros2_ws/install/setup.bash` | Assumes `~/ros2_ws` | Resolve workspace root relative to script path (`SCRIPT_DIR/../../..`) |
| Host `~/.bashrc` | 119, 123 | `source ~/ros2_ws/install/setup.bash`, `GZ_SIM_RESOURCE_PATH` appending `~/ros2_ws/install/fcm_digital_twin/share` | Workstation-only shell assumption | Keep local convenience aliases out of package requirements |

---

## Group C — Network, Interface, Port & Device Hardcodes

| Component / File | Lines | Hardcoded Value | Risk / Impact | Proposed Fix |
| --- | --- | --- | --- | --- |
| `Infrastructure_as_Code/autostart/start_server.sh`<br>`Infrastructure_as_Code/autostart/smart_launcher.py`<br>`Infrastructure_as_Code/configs/cyclonedds_server.xml` | 4<br>58<br>15 | `192.168.31.100` (robot static IP) | Breaks whenever router subnet / robot DHCP lease / VPN changes | Factor into shared env/config (`.env` or mDNS/Tailscale hostname such as parameterizable `SMART_ROBOT_IP`) |
| `Infrastructure_as_Code/configs/cyclonedds.xml`<br>`Infrastructure_as_Code/configs/cyclonedds_server.xml` | 6<br>7 | `ros0` (robot NIC), `wlp82s0` (operator laptop Wi-Fi NIC) | CycloneDDS fails to start if Wi-Fi/Ethernet interface name differs on another host | Generate CycloneDDS XML from template / env var or auto-detect active interface |
| `Infrastructure_as_Code/autostart/smart_launcher.py`<br>`smart_server/smart_server/web_server.py`<br>`Infrastructure_as_Code/web_ui_2.0/src/components/layout/ConnectionBox.vue`<br>`Infrastructure_as_Code/web_ui_2.0/src/components/layout/DigitalTwin3D.vue`<br>`Infrastructure_as_Code/web_ui_2.0/src/components/layout/composables/useSdfWorlds.js`<br>`Infrastructure_as_Code/web_ui_2.0/src/three/robotModel.js` | 67–68<br>161<br>43<br>489<br>32, 94<br>61, 92 | Fixed HTTP port `8080` and `rosbridge` WebSocket port `9090`, plus `/install/<pkg>/share/<pkg>/...` HTTP paths | Port collisions or reverse-proxy / Vite dev port mismatch (`window.location.hostname:8080`) | Use `window.location.origin` (or configurable URL/port via Vite env / query / config JSON) in Web UI, and derive paths from `/packages/<pkg>/...` consistently |
| `Infrastructure_as_Code/autostart/start_robot.sh`<br>`smart_radiation/smart_radiation/accurad_protocol.py` | 44–45<br>14 | `/dev/esp32s3`, `/dev/accurad` | Requires matching `/etc/udev/rules.d/` entries on **both** laptop and Raspberry Pi (`99-linorobot.rules` etc.) | Store versioned udev rules template under `Infrastructure_as_Code/configs/` with clear serial/VID:PID setup instructions; keep ROS params (`port`) overridable |
| `Infrastructure_as_Code/autostart/start_robot.sh`<br>`Infrastructure_as_Code/autostart/start_server.sh` | 17 (robot)<br>20 (server) | Zenoh DDS bridge `--allow` regex list (`^rt/smart_telemetry$`, `^rt/radiation_map$`, `^rt/radiation_image/compressed$`, `^rt/radiation/status$`, etc.) | Intentional bandwidth filter, but easy to drift between robot and server scripts when adding/renaming topics | Centralize allowlist in a shared config/file read by both scripts; keep `/radiation/dose` local on robot unless cross-host debugging or split-host sensor placement is needed |

---

## Recommended Next Steps Order

1. **Completed:** `smart_sim2real/worlds/*.sdf` mesh URI portability + `sim.launch.py` / ament hook `GZ_SIM_RESOURCE_PATH`.
2. **Next (quick wins):** Versioned udev rules template in `Infrastructure_as_Code/configs/` for `/dev/accurad` & `/dev/esp32s3` + fix `ArmAutoTab.vue` / `radiation_bringup.launch.py` / `web_server.py` workspace path resolution.
3. **Then:** Replace `/home/oleksandr/cyclonedds.xml` and `~/ros2_ws/...` hardcoded shell commands in `mission_manager.py`, `twin_orchestrator.py`, `recovery_relocalizer.py`, and `smart_radiation_plugins` C++ fallbacks.
4. **Finally:** Centralize network configuration (`ROBOT_IP`, NIC names, Zenoh allowlist, HTTP/WS ports) in `Infrastructure_as_Code/`.
