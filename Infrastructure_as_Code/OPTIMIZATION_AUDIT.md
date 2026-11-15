# Smart Robotics Performance & Optimization Audit

This document records baseline hardware profiling from **Raspberry Pi 5** (captured over SSH during an idle bringup after `rad_off` with SLAM + Nav2 + Camera + LiDAR + Micro-ROS + Radiation + Zenoh Bridge active) together with the server-side impact observed in `smart_server`, and tracks the prioritized optimization backlog.

---

## 1. Raspberry Pi 5 Baseline Snapshot

**Hardware & OS State (`192.168.31.100`, `raspberry-pi5`):**
* **CPU:** 4x ARM64 cores @ `2.40 GHz` (`ondemand` governor)
* **Thermal & Power:** `58.4°C`, `throttled=0x0` (no thermal or under-voltage throttling)
* **Memory / Swap / Disk:** `3.9 GiB` RAM (`1.3–1.4 GiB` used, `2.5–2.6 GiB` available), `3.0 GiB` swap (`0 B` used), `/dev/mmcblk0p2` `57G` (`25G` / `46%` used)
* **System Load (`uptime` / `vmstat 1 4`):** `load average: 7.59–23.00`, ~41–48% total CPU (`~52% idle`), runnable queue `r = 1, 23, 26, 69`, kernel time `sy = 18–22%`
* **Kernel Interrupts & Context Switches:** `13,941–14,109 interrupts/s`, **`36,394–39,944 context switches/s`**
  * `/proc/interrupts` (2s avg): `IRQ 13 arch_timer 5,394.5/s`, `IPI1 3,610.5/s`, `IPI0 3,592.0/s`, `IRQ 140 xhci-hcd:usb4 1,400.0/s`, `IRQ 172 iwlwifi:default_queue 365.5/s`, `IRQ 14 mailbox 152.5/s`
* **Network / UDP Counters (`nstat`, 1s delta):** `+14,745 UdpInDatagrams/s`, `+4,110 UdpOutDatagrams/s`, `UdpRcvbufErrors: 2,005`, `+341 IpExtInMcastPkts/s`, `+400 IpExtOutMcastPkts/s`

> **Primary Bottleneck:** In the local CycloneDDS configuration (`~/cyclonedds.xml` on `ros0` `10.0.0.1/24`), `<AllowMulticast>true</AllowMulticast>` and `<SharedMemory><Enable>false</Enable></SharedMemory>` force ~27 local ROS 2 processes to exchange traffic over kernel UDP + multicast sockets. Even quiet nodes (`robot_state_publisher`) wake up inside `recvMC` `304–376 times/s`. Combined with 11 separate Nav2 processes (~90–95% of 1 core total) and `/bond` at `198.94 Hz`, this drives ~36k–40k context switches/s and causes scheduler starvation spikes (`load average` up to `23.0`, `ekf_node` timing misses).

### Subsystem Resource Breakdown (Idle)

| Subsystem / Node | CPU (%) | Context Sw/s | RSS Memory | Topic / Key Metric |
| :--- | :---: | :---: | :---: | :--- |
| **Nav2 + SLAM (11 + 1 procs)** | **~90–95% (1 core)** | **~14,800+** | **—** | **`/bond`: `198.94 Hz` (`18.18 KB/s`)** |
| `lifecycle_manager_navigation` | `14.7–17.0%` | `1,641/s` | — | Main thread alone `11.0%` CPU |
| `controller_server` | `7.8–9.1%` | `1,314.5/s` | — | WARN: `verbose` missing, checker params |
| `behavior_server` | `6.9–8.5%` | `1,305.5/s` | — | — |
| `bt_navigator` | `6.9–8.5%` | `1,297.5/s` | `49.2 MB` | — |
| `route_server` | `6.9–8.0%` | `1,292/s` | — | Unused in BT (`use_route:=false` candidate) |
| `opennav_docking` (`docking_server`) | `5.9–8.0%` | `1,264.5/s` | — | WARN: no dock database; unused right now |
| `collision_monitor` | `6.9–7.7%` | `1,276/s` | — | — |
| `planner_server` | `5.9–7.6%` | `1,249/s` | `41.4 MB` | ERROR: inflation vs non-circular footprint |
| `smoother_server` | `5.9–7.5%` | `1,280/s` | — | — |
| `velocity_smoother` | `4.9–6.5%` | `1,147/s` | — | — |
| `waypoint_follower` | `4.9–6.5%` | `1,103/s` | — | — |
| `async_slam_toolbox_node` | `3.9–4.0%` | `853/s` | `44.3 MB` | `/map`: `1.25 Hz` (`8.84 KB/s`) |
| **Camera (`camera_ros`, CSI `imx219`)** | **`16.7–23.0%`** | **`1,012/s`** | **`106.7 MB` (`2.6%`)** | `800x600`, `XRGB8888`, JPEG `25`, `~17 Hz` (`338.21 KB/s`) |
| **PC Operator Side (`smart_server`)** | `40.6%` / `30.9%` / `22.5%` | — | — | `rosbridge_websocket` / `QtWebEngineProcess` / `smart_launcher.py` (Wi-Fi RTT `1.34–56.64 ms`, avg `15.35 ms`) |
| **`micro_ros_agent -v4`** | **`7.8–17.9%`** (`10.0%` avg) | **`2,281/s`** | **`53.9 MB`** | `/odom/unfiltered` `91.47 Hz` (`64.67 KB/s`), `/imu/data` `92.22 Hz` (`29.18 KB/s`) |
| **`ekf_node` (`robot_localization`)** | **`7.8–8.5%`** | **`1,225/s`** | **`30.3 MB`** | `/odom` `29.99 Hz` (`21.20 KB/s`), ERROR: `0.034..0.082s` |
| **Radiation (`radiation_session`, idle)** | **`~9–24%` total** | **`~3,090/s`** | **`166.6 MB`+** | — |
| `radiation_field_server` | `2.0–9.8%` | `786/s` | `166.6 MB` (`4.0%`) | `RuntimeWarning` at line `229`; `/map` DURABILITY WARN |
| `radiation_manager` | `2.0–6.5%` | `762/s` | `63.3 MB` | `/radiation/status` `depth=10, TRANSIENT_LOCAL` |
| `virtual_geiger_node` | `2.0–4.0%` | `767.5/s` | — | — |
| `radiation_mapper_node` | `3.0–4.1%` | — | — | Map weights mismatch WARN (`800x800` vs `1200x800`) |
| **Base / LiDAR / Bridge** | — | — | — | — |
| `sllidar_node` (`/dev/ttyUSB0`) | `2.9–4.2%` | `835/s` | — | `/scan`: `7.75 Hz` (`65.82 KB/s`) |
| `joint_state_publisher` | `2.9–4.1%` | `700/s` | `67.2 MB` | `/joint_states`: `10.00 Hz` |
| `robot_state_publisher` | `2.0–2.8%` | `706/s` | — | `recvMC 304.5/s`; `/tf`: `50.23 Hz` |
| `zenoh-bridge-dds` | `2.9–4.1%` | `791.5/s` | — | Bridges Pi DDS <-> Server over Wi-Fi |
| `telemetry_mux` | `2.9–3.2%` | `700/s` | — | `/smart_telemetry`: `5.00 Hz` |
| `smart_control` Python nodes | `~1–4.1%` each | — | `64–68 MB` each | Includes `mission_manager`, `teleop_mux`, etc. |

---

### 1.1 Post-Change Verification on Raspberry Pi 5 (Commit `fdd168e`)

Measured after deploying `use_composition:=true`, `use_docking:=false`, `use_route:=false`, and removing `micro_ros_agent -v4`:

| Metric / Process | Baseline (Before) | Without `radiation_session` | Apples-to-Apples **With `radiation_session`** |
| :--- | :---: | :---: | :---: |
| **`top` Idle / System %** | ~`52% id` (`sy 18–22%`) | **`75.3% id` (`sy 8.5–11%`)** | **`76.4% id` (`13.8 us, 8.7 sy`)** |
| **Load average** | `7.59–23.00` | `5.86` *(5 min post-boot)* | `5.05–5.31` *(13 min uptime, post-restart)* |
| **Runqueue (`vmstat r`)** | `1, 23, 26, 69` | **`0–1`** | **`0–1`** |
| **Context switches (`vmstat cs`)** | `36,394–39,944 /s` | **`16,179–17,732 /s`** | **`18,173–22,079 /s`** (**~2× lower**) |
| **Interrupts (`vmstat in`)** | `13,941–14,109 /s` | `10,339–11,019 /s` | `10,763–11,262 /s` |
| **Nav2** | ~`90–95%` of 1 core (11 procs) | **`29.4%` (`86.8 MB` RSS)** in 1 container | **`26.5%` (`95.0 MB` RSS)** in 1 container |
| **`/bond` rate** | `198.94 Hz` (inter-process UDP) | **`160.05 Hz`** (in-container) | `~160 Hz` *(8 active servers; not re-sampled after rad start)* |
| **`micro_ros_agent`** | `7.8–17.9%` (`53.9 MB`) | **`6.9%` (`48.1 MB`)** | **`5.9%` (`50.0 MB`)** |
| **`ekf_node`** | `7.8–8.5%` + steady overruns | **`6.9%`**, `30.02 Hz`, 0 errors | **`5.9%`**, startup-only overruns (`11–14s` after nav restart), 0 steady-state errors |
| **UDP In / Out (`nstat`)** | `+14,745` / `+4,110 /s` | `+5,620` / `+3,115 /s` | **`+4,069` / `+1,496 /s`** (**~3.6× / 2.7× lower**) |
| **UDP Multicast In / Out** | `+341` / `+400 /s` | `+189` / `+227 /s` | **`+138` / `+174 /s`** |
| **`UdpRcvbufErrors`** | `2,005` total | **`0 (+0/s)`** | `18,942` startup burst, **`+0/s` steady** |
| **Memory Used / Avail** | `1.3–1.4` / `2.5–2.6 GiB` | `1.0` / `2.9 GiB` | `1.2` / `2.6 GiB` |
| **Temp / Throttling** | `58.4°C`, `0x0` | `47.2°C`, `0x0` | `57.6°C`, `0x0` |

> **Field Result:** Restarting `mission_nav_session` and launching `radiation_session` worked smoothly together; active Nav2 goals (`controller_server` + BT recovery + goal completion) executed inside `/nav2_container` without steady-state `ekf_node` timing misses or UDP buffer drops.

---

## 2. Optimization Roadmap Summary

| Area | Item | Impact | Risk | Status |
| :--- | :--- | :---: | :---: | :--- |
| **Micro-ROS Agent** | Remove `-v4` verbose serial logging in `start_robot.sh` | Low-Med | Very Low | **Done & Pi-Verified** |
| **Nav2 Bringup** | Own `navigation_launch.py` in `smart_nav` with `use_composition`, `use_docking`, `use_route` flags | **High** | Low-Med | **Done & Pi-Verified** |
| **Nav2 Config** | Fix `planner_server` inflation warning vs non-circular footprint; audit `controller_server` checker/verbose warnings | Med | Low | **Planned** |
| **Nav2 Bond** | Tune `bond_heartbeat_period` / `bond_timeout` after measuring composed Nav2 `/bond` load | Med | Low-Med | **Planned** |
| **ESP32 Firmware + EKF** | Decouple 100 Hz PID/Ramp from ~50 Hz ROS publish; fix `Ramp.h` unused `dt`; re-test `ekf_node` 30 Hz overrun | **High** | Med | **Planned** |
| **Base State / URDF** | Lightweight Python/C++ `joint_state_publisher` replacement + audit standalone vs `smart_master` `rsp`/`jsp` launch overlap | Low-Med | Low | **Planned** |
| **Middleware (RMW)** | Evaluate native `rmw_zenoh_cpp` (skip CycloneDDS Iceoryx broker for now) to cut UDP multicast & bridge overhead | **Very High** | Med-High | **Deferred (Future)** |
| **Camera (`camera_ros`)** | Test `RGB888`/`NV21` (instead of `XRGB8888`) and/or `10–12 Hz` FPS cap to drop RPi5 & PC `rosbridge` CPU | Med | Low-Med | **Deferred (After hardware stabilization)** |
| **Radiation & QoS** | Fix `radiation_field_server.py:229` cast warning, `radiation_manager` `depth=1`, `/map` Zenoh durability/weights mismatch | Low | Low | **Planned** |

---

## 3. Detailed Optimization Notes

### A. Navigation Stack (`smart_nav`)
* **Done & Verified on Local PC + Raspberry Pi 5:**
  * Copied Jazzy [`navigation_launch.py`](../smart_nav/launch/navigation_launch.py) into `smart_nav` and wired it into [`bringup_mapping.launch.py`](../smart_nav/launch/bringup_mapping.launch.py) and [`bringup_lifelong.launch.py`](../smart_nav/launch/bringup_lifelong.launch.py).
  * Added `use_docking` (default `False`) and `use_route` (default `False`) flags that simultaneously skip launching `opennav_docking` / `nav2_route` AND remove `'docking_server'` / `'route_server'` from `lifecycle_manager_navigation`'s `node_names` list (avoiding lifecycle manager startup hangs while keeping `nav2_params.yaml` intact for future activation).
  * Added `use_composition` (default `True`) + `create_container` + `container_name` (running `rclcpp_components/component_container_isolated` named `nav2_container`), collapsing up to 11 separate Nav2 OS processes into a single container process while keeping every ROS node name, parameter service, costmap service, and action identical. Loaded `lifecycle_manager_navigation` first inside `nav2_container` so `rcl preshutdown` disarms bond supervision before the servers tear down (eliminating false 4 s bond failures and avoiding `SIGINT` -> `SIGTERM` escalation).
  * **Compatibility note (`smart_sandbox`):** [`block2b_logger.py`](../smart_sandbox/smart_sandbox/block2b_logger.py#L271-L334) discovers Nav2 processes by per-server executable name (`controller_server`, `planner_server`, ..., `route_server`). When `use_route:=false` or `use_composition:=true`, missing process names safely fall back to `0.0`, though composed runs would need `component_container_isolated` tracking if per-process CPU logging is needed in sandbox benchmarks.
  * **Compatibility note (`mission_manager`):** [`mission_manager.py`](../smart_control/smart_control/mission_manager.py) manages `mission_nav_session` and `radiation_session` as independent `tmux` sessions and interacts via ROS topics/services/parameters (`set_speed`, `clear_costmap`, `save_map`, `rad_on`/`rad_off`), so composed Nav2 requires zero changes to `mission_manager.py`. (Minor housekeeping note: `Popen(['tmux', 'new-session', ...])` leaves 1 harmless `[tmux: client] <defunct>` zombie entry until `mission_manager` exits.)
* **Next Cleanups:**
  1. Investigate `[planner_server] [ERROR] Inflation layer either not found or inflation is not set sufficiently for optimized non-circular collision checking capabilities...` in [`nav2_params.yaml`](../smart_nav/config/nav2_params.yaml) (`global_costmap.inflation_layer.inflation_radius` vs footprint circumradius in `SmacPlanner2D`).
  2. Clean up `[controller_server] [WARN] Parameter controller_server.verbose not found` / `No goal/progress checker specified` and inspect whether `bond_heartbeat_period` still needs tuning inside `nav2_container` (`160 Hz` intra-process vs `~199 Hz` multi-process previously).

### B. ESP32-S3 Firmware (`ugv_tracked_firmware`) & `ekf_node` Pipeline
* **Removed `-v4`:** Dropped `-v4` from `micro_ros_agent serial --dev /dev/esp32s3` in [`start_robot.sh`](autostart/start_robot.sh#L52) to cut serial/stdout logging pressure during `91–92 Hz` bursts.
* **Observed Firmware Issues (`ugv_tracked` repo):**
  * `LOOP_INTERVAL_S = 0.01` runs encoder PID, `Ramp`, and `/odom/unfiltered` + `/imu/data` publishing in the same `100 Hz` loop (`91.47 Hz` + `92.22 Hz` over USB CDC serial -> `2,281 ctxt/s` in `micro_ros_agent`).
  * `Ramp.h` computes `max_step = max_acceleration * dt` without using it, clamping with `constrain(...)` per tick instead—meaning changing the loop period would alter acceleration curves unless `dt` scaling is fixed first.
* **Planned Pipeline Synchronization:**
  1. Fix `Ramp.h` to actually scale step limits by `dt` (so ramp behavior becomes rate-independent).
  2. Keep internal PID + ramp loop at `100 Hz` on ESP32-S3, while throttling micro-ROS telemetry publish (`/odom/unfiltered`, `/imu/data`) to **`50 Hz`** (matched cleanly to `ekf_node`'s `30 Hz` or `50 Hz` update rate) and verifying serial buffer / Wi-Fi behavior before changing `ekf.yaml` covariances.
  3. Re-measure `ekf_node` timing on RPi5 after composed Nav2 + 50 Hz firmware publish to see if `[ERROR] Failed to meet update rate! Took 0.034..0.082s` disappears naturally once scheduler contention drops.

### C. Base State Publishers (`joint_state_publisher` & `robot_state_publisher`)
* Stock `joint_state_publisher` burns `~67.2 MB` RSS and `2.9–4.1% CPU` (`700 ctxt/s`) just relaying `/joint_states` at `10.00 Hz`.
* **Planned:**
  1. Replace stock `joint_state_publisher` in hardware bringup with a tiny, standalone minimal Python or C++ node dedicated strictly to track/base wheel or default joint state aggregation—do **not** merge it into `telemetry_mux` or `trajectory_bridge` because base navigation must work independently of the manipulator.
  2. Audit where `robot_state_publisher` and `joint_state_publisher` are started across standalone robot scripts vs `smart_master` bringups so duplicate/overlapping publishers never occur.

### D. Middleware Architecture (CycloneDDS -> Future `rmw_zenoh_cpp`)
* **Current Decision:** Keep the isolated CycloneDDS (`ros0`, `<AllowMulticast>true</AllowMulticast>`, `<SharedMemory><Enable>false</Enable></SharedMemory>`) + `zenoh-bridge-dds` setup untouched for now; do **not** install Iceoryx (`iox-roudi`) shared-memory broker yet.
* **Future Migration (`rmw_zenoh_cpp`):** Replacing `cyclonedds` + `zenoh-bridge-dds` with native ROS 2 Jazzy `rmw_zenoh_cpp` + a local `rmw_zenohd` router eliminates both DDS UDP multicast discovery floods across ~27 local processes AND the `zenoh-bridge-dds` translation process (`2.9–4.1% CPU`, `791.5 ctxt/s`). Test isolated on PC <-> Pi once hardware bringup is stable.

### E. CSI Camera (`camera_ros` on RPi5 + `rosbridge` on PC)
* **Current Decision:** Leave RPi5 `~/ros2_ws/run_camera.launch.py` (`800x600`, `XRGB8888`, `jpeg_quality: 25`, `FrameDurationLimits: [66666, 66666]`) working as-is until base/Nav2 tests finish.
* **Future Candidates:**
  * Converting `XRGB8888` (32-bit/px) to JPEG costs extra CPU/memory bandwidth vs `RGB888` (24-bit/px) or `NV21` / hardware-friendly format—worth A/B benchmarking inside `camera_ros`.
  * Capping compressed camera publish to `10–12 Hz` (when ~17 Hz isn't needed for teleop) should lower both RPi5 (`16.7–23.0%` CPU) and PC-side `rosbridge_websocket` (`40.6%` CPU) + `QtWebEngineProcess` (`30.9%` CPU).

### F. Minor QoS & Radiation Cleanups
* [`radiation_field_server.py`](../smart_radiation/smart_radiation/radiation_field_server.py#L229): fix `RuntimeWarning: invalid value encountered in cast` at grid value casting.
* [`radiation_manager.py`](../smart_radiation/smart_radiation/radiation_manager.py): switch `/radiation/status` QoS history depth from `10` to `1` (`TRANSIENT_LOCAL`) so late CLI `--once` subscribers only see the latest state instead of replaying `"STARTING"` + `"ACTIVE"`.
* Investigate `zenoh-bridge-dds` / bare DDS participant publishing `VOLATILE` on `/map` (causing `DURABILITY_QOS_POLICY` warning in `radiation_field_server`) and `radiation_mapper_node` map-weights dimension mismatch warning (`800x800` vs `1200x800`).
