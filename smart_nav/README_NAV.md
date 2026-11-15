# `smart_nav` Navigation Field Notes: Tuning, Pitfalls & Lessons Learned

Production engineering field notes and battle-tested tuning history for the **`smart_nav`** Nav2 + SLAM Toolbox + ALARA Radiation stack in `smart_robotics`. Rather than generic Nav2 documentation, this document records the exact parameter invariants, empirical tradeoffs, root causes of real navigation failures ("rakes" / post-mortems), and verified recovery fixes from Gazebo Sim2Real and Raspberry Pi onboard testing.

---

## 1. Platform Constraints & Package Layout

### Hardware & Kinematic Reality
* **Drivetrain:** Tracked differential-drive UGV (`motion_model: "DiffDrive"`, `vy_max: 0.0`). It **cannot move laterally (no strafing)**, has higher rotational scrub resistance on tracks than wheeled platforms, and has a **rectangular chassis** whose corner circumradius is noticeably larger than its half-width/inscribed radius:
  * `local_costmap` footprint (`[±0.26, ±0.22]`): half-width `0.22 m`, **corner radius $\sqrt{0.26^2 + 0.22^2} \approx 0.341\text{ m}$**.
  * `global_costmap` footprint (`[±0.32, ±0.29]`): inscribed radius `0.29 m`, **corner radius $\sqrt{0.32^2 + 0.29^2} \approx 0.432\text{ m}$**.
* **Onboard Compute Budget (Raspberry Pi):** MPPI rollouts (`batch_size * time_steps`) and costmap evaluation run on limited ARM CPU cores alongside SLAM Toolbox, Gazebo/hardware bridges, and radiation nodes. Sampling budget must stay compact.

### Package Files
* Navigation & costmap config: [`config/nav2_params.yaml`](config/nav2_params.yaml)
* Custom Behavior Trees:
  * [`config/navigate_to_pose_w_replanning_and_recovery.xml`](config/navigate_to_pose_w_replanning_and_recovery.xml)
  * [`config/navigate_through_poses_w_replanning_and_recovery.xml`](config/navigate_through_poses_w_replanning_and_recovery.xml)
* SLAM Toolbox configs: [`config/slam_lifelong.yaml`](config/slam_lifelong.yaml), [`config/slam_mapping.yaml`](config/slam_mapping.yaml)
* Launch entry points: [`launch/bringup_lifelong.launch.py`](launch/bringup_lifelong.launch.py), [`launch/bringup_mapping.launch.py`](launch/bringup_mapping.launch.py), [`launch/slam_lifelong.launch.py`](launch/slam_lifelong.launch.py), [`launch/slam_mapping.launch.py`](launch/slam_mapping.launch.py)
* Radiation config & plugins (external packages integrated here):
  * [`../smart_radiation/config/radiation_params.yaml`](../smart_radiation/config/radiation_params.yaml)
  * [`../smart_radiation_plugins/src/radiation_layer.cpp`](../smart_radiation_plugins/src/radiation_layer.cpp)
  * [`../smart_radiation_plugins/src/alara_speed_reflex.cpp`](../smart_radiation_plugins/src/alara_speed_reflex.cpp)

---

## 2. Architecture & Data Flow

```text
  nav_coordinator / tactical_executor / Web UI
                      │  (NavigateToPose / NavigateThroughPoses)
                      ▼
               [ bt_navigator ]  ◄── Custom BTs in smart_nav/config/*.xml
                 │          │
      1 Hz plan  ▼          ▼  10 Hz control
       [ planner_server ]   [ controller_server ]
       (SmacPlanner2D)      (MPPIController + SimpleGoalChecker + SimpleProgressChecker)
             │                        │
             ▼                        ▼  cmd_vel_nav
      [global_costmap]       [ velocity_smoother ] ──► cmd_vel_smoothed
       - static_layer                 │
       - obstacle_layer               ▼
       - inflation_layer     [ collision_monitor ] (FootprintApproach)
       - radiation_layer              │
         (C_max = 220)                ▼  cmd_vel
                             Base Firmware / Gazebo DiffDrive
```

*Note on speed overrides:* `mission_manager` adjusts `FollowPath.vx_max` dynamically (`set_speed:<m/s>`), while `alara_speed_reflex_node` (when enabled) publishes percentage `/speed_limit` messages consumed by `controller_server` (`speed_limit_topic: speed_limit`). Both respect `velocity_smoother.max_velocity: [1.5, 0.0, 2.5]`.

---

## 3. MPPI Controller (`FollowPath`) — Raspberry Pi Tuning & Critics

Configured in [`config/nav2_params.yaml`](config/nav2_params.yaml#L86-L171).

### Fixed CPU-Budget Parameters
| Parameter | Current Value | Why It Must Stay Here |
|---|---:|---|
| `controller_frequency` | `10.0` Hz | `100 ms` loop period; leaves headroom on Raspberry Pi. Dictates minimum `bt_navigator.default_server_timeout`. |
| `time_steps` | `15` | Combined with `model_dt: 0.1`, gives a **`1.5 s` lookahead horizon**. |
| `model_dt` | `0.1` s | Matches `controller_frequency` (`10 Hz`). |
| `batch_size` | `500` | Maximum trajectory count safe for real-time Pi CPU budget. |
| `iteration_count` | `1` | Single-pass MPPI per tick. Critical implication: noise stds must stay wide enough for 1-shot coverage! |
| `temperature` | `0.3` | Controls softmax sharpness across the 500 rollouts. |
| `gamma` | `0.015` | Control cost regularization. |
| `vx_min` / `vx_max` | `-0.35` / `1.5` (YAML) | Negative `vx_min` (`-0.35`) is mandatory so MPPI can sample small reversing corrections; never set `0.0`. Runtime default often overridden via `set_speed` (e.g., `0.6`). |
| `vx_std` / `wz_std` | `0.6` / `0.4` | **Do not shrink `vx_std` or inflate `wz_std` recklessly (see Pitfall #1 below).** |

### Critic Inventory & Verified Behavior
| Critic | Key Parameters (Current) | Role & Interaction Notes |
|---|---|---|
| `ConstraintCritic` | `cost_weight: 5.0` | Penalizes trajectories exceeding kinematic limits. |
| `CostCritic` | `cost_weight: 6.0`, `near_collision_cost: 253`, `critical_cost: 300.0`, `consider_footprint: true`, `collision_cost: 1000000.0`, `near_goal_distance: 1.0`, `trajectory_point_step: 2` | Evaluates full oriented footprint against `local_costmap` when cell cost $\ge 253$ (`INSCRIBED`) or footprint check threshold triggers. See **Pitfall #3** on `near_collision_cost`. |
| `PathAlignCritic` | `cost_weight: 6.0`, `max_path_occupancy_ratio: 0.25`, `trajectory_point_step: 2`, `threshold_to_consider: 0.5`, `offset_from_furthest: 6`, `use_path_orientations: true` | Keeps the robot centered and **oriented along the path** before entering tight doorways. Disables within `0.5 m` of goal so `GoalAngleCritic` can rotate cleanly. |
| `PathFollowCritic` | `cost_weight: 5.0`, `offset_from_furthest: 2`, `threshold_to_consider: 1.4` | Pulls the trajectory endpoint forward along the path. Disables within `1.4 m` of goal (must stay smaller than `nav_coordinator.sw_min_end_dist = 1.80 m` so sliding-window routes do not stall). |
| `PathAngleCritic` | `cost_weight: 3.0`, `offset_from_furthest: 4`, `threshold_to_consider: 0.5`, `max_angle_to_furthest: 1.57`, `mode: 0` | Prevents large heading misalignment (`mode: 0` = Forward Preference) relative to `offset_from_furthest` ahead. |
| `PreferForwardCritic` | `cost_weight: 14.0`, `threshold_to_consider: 0.8` | Penalizes reverse motion outside `0.8 m` from goal so the robot drives forward normally, while permitting reverse corrections close to the goal. |
| `GoalCritic` | `cost_weight: 5.0`, `threshold_to_consider: 1.4` | Attracts $(x, y)$ position toward goal within `1.4 m`. |
| `GoalAngleCritic` | `cost_weight: 3.0`, `threshold_to_consider: 0.5` | Aligns final yaw when within `0.5 m` of the goal. |

---

## 4. Global Planner (`SmacPlanner2D`) & Smoother Interaction

Configured under `planner_server.GridBased` in [`config/nav2_params.yaml`](config/nav2_params.yaml#L263-L279):

```yaml
GridBased:
  plugin: "nav2_smac_planner::SmacPlanner2D"
  tolerance: 0.5
  allow_unknown: true
  cost_travel_multiplier: 10.0
  smoother:
    tolerance: 1.0e-10
    max_iterations: 20
    w_data: 0.5
    w_smooth: 0.1
    do_refinement: false
    refinement_num: 1
```

### Critical Implementation Rule (Verified in ROS 2 Jazzy `libnav2_smac_planner_2d.so`)
* During A* search, `cost_travel_multiplier: 10.0` strongly penalizes high-cost cells (`1..252`), routing the raw path right through the **geometric center** of doorways (e.g., `x = 8.373` on `213_map`) and around high-cost `RadiationLayer` zones.
* **HOWEVER**, `nav2_smac_planner::Smoother::smoothImpl` **ignores gradient inflation costs `1..252`**! It only rejects a smoothing step if a point lands directly on `cost == 253` (`INSCRIBED_INFLATED_OBSTACLE`) or `cost == 254` (`LETHAL_OBSTACLE`).
* Therefore, `w_smooth` must **never dominate `w_data`** over hundreds of iterations, or the smoother will pull every 90° doorway turn diagonally inward right onto the `cost = 252` inscribed edge!

---

## 5. Footprints, Inflation, Collision Monitor & Progress/Goal Checkers

### Deliberate Asymmetric Footprint Design
| Layer / Node | Parameter | Current Value | Purpose |
|---|---|---:|---|
| `local_costmap` | `footprint` | `[[-0.26, -0.22], [-0.26, 0.22], [0.26, 0.22], [0.26, -0.22]]` | Tighter physical clearance (`~2–3 cm` safety margin) so the robot can physically thread `~0.75–0.85 m` doorways without false collisions, while still stopping before track/frame contact. |
| `local_costmap` | `inflation_radius` / `cost_scaling_factor` | `0.70` / `3.0` | Provides smooth cost gradient around `/scan` obstacles (`rolling_window: true`, `4x4 m`, `0.05 m/cell`). |
| `global_costmap` | `footprint` | `[[-0.32, -0.29], [-0.32, 0.29], [0.32, 0.29], [0.32, -0.29]]` | Larger footprint keeps global `/plan` farther from static map walls. Note: because `global_costmap` inscribed radius is `0.29 m` (vs `0.22 m` local), getting too close to a wall corner triggers `"Start occupied"` on `global_costmap` before `local_costmap` flags lethal! |
| `global_costmap` | `inflation_radius` / `cost_scaling_factor` | `0.7` / `3.0` | Smoothly centers A* through doorways when combined with `cost_travel_multiplier: 10.0`. |
| `collision_monitor` | `FootprintApproach` | `time_before_collision: 0.8`, `min_points: 6`, `scan min_height: 0.15` | Independent last-line safety shield between `cmd_vel_smoothed` and `cmd_vel` using `/local_costmap/published_footprint`. |
| `general_goal_checker` | `xy_goal_tolerance` / `yaw_goal_tolerance` | `0.15` m / `0.15` rad | Exactness at waypoint completion. (`stateful: true`). |
| `progress_checker` | `required_movement_radius` / `movement_time_allowance` | `0.35` m / `4.5` s | Detects stalled/wedged motion within `4.5 s` and aborts `FollowPath` so BT recovery (`BackUp`) can trigger promptly. |

---

## 6. Custom Behavior Trees & Recovery Pipeline

Default Nav2 Jazzy BTs (`/opt/ros/jazzy/share/nav2_bt_navigator/behavior_trees/...`) had two fatal incompatibilities with this robot and were replaced with local XMLs in `smart_nav/config/`:
* [`config/navigate_to_pose_w_replanning_and_recovery.xml`](config/navigate_to_pose_w_replanning_and_recovery.xml)
* [`config/navigate_through_poses_w_replanning_and_recovery.xml`](config/navigate_through_poses_w_replanning_and_recovery.xml)

### Recovery Sequence Design
1. Inside `PipelineSequence` (`NavigateWithReplanning`), `RateController` replans at `1.0 Hz` (`0.333 Hz` for `NavigateThroughPoses`). Context recoveries attempt `ClearGlobalCostmap` / `ClearLocalCostmap` once before escalating.
2. When replanning or control fails, the outer `RecoveryNode` (`number_of_retries="6"`) enters `ReactiveFallback` directly without `WouldAPlannerRecoveryHelp` / `WouldAControllerRecoveryHelp` gating (**see Pitfall #6**).
3. `RoundRobin` executes:
   1. `ClearingActions`: Clear Local Costmap → Clear Global Costmap → **`BackUp(backup_dist="0.40", backup_speed="0.20")`**
   2. `Spin(spin_dist="1.57")`
   3. `Wait(wait_duration="3.0")`
   4. `BackUp(backup_dist="0.45", backup_speed="0.20")`

*Note on `BackUp` safety:* `nav2_behaviors::BackUp` inherits `DriveOnHeading::isCollisionFree`, checking the local costmap for `behavior_server.simulate_ahead_time: 2.0` s along the reverse path before commanding motion.

---

## 7. Catalog of Encountered Pitfalls ("Rakes" & Post-Mortems)

### Pitfall 1 — Shrinking `vx_std` / Raising `wz_std` with `iteration_count: 1`
* **Symptom:** At `0.6 m/s`, robot failed to brake smoothly before turns and swung sharply into doorway wall corners (`max wz` bias).
* **Root Cause:** With `iteration_count: 1` and `batch_size: 500`, shrinking `vx_std` (`0.6 -> 0.45`) deprived the single noisy sample batch of strong deceleration trajectories (`0.6 -> 0.0 m/s` within `1.5 s`), while raising `wz_std` (`0.4 -> 0.50`) flooded rollouts with aggressive turns.
* **Rule:** Keep `vx_std: 0.6`, `wz_std: 0.4`.

### Pitfall 2 — Over-Smoothing in `SmacPlanner2D` Caused Doorway Wall Crashes
* **Symptom:** Orange global `/plan` visibly sliced straight across doorway wall corners on `213_map` (`y = -0.30` doorway corner), leading the robot right into physical contact at `(8.23, -0.28)` under a diagonal heading.
* **Root Cause:** `SmacPlanner2D::Smoother::smoothImpl` ignores inflation costs `1..252` and only stops at `253/254`. The prior config (`max_iterations: 300, w_data: 0.1, w_smooth: 0.3, do_refinement: true, refinement_num: 2`) ran `900` smoothing iterations with `w_smooth = 3x w_data`, dragging the turn onto `cost = 252` (`0.29 m` from the wall), inside the `0.34–0.43 m` rectangular corner sweep radius.
* **Fix:** Reduced smoother pull (`max_iterations: 20, w_data: 0.5, w_smooth: 0.1, do_refinement: false, refinement_num: 1`), keeping the `/plan` aligned through doorway center (`x = 8.373`) until straight entry.

### Pitfall 3 — Setting `CostCritic.near_collision_cost: 195` Broke Narrow Doorways
* **Symptom:** Repeated `[controller_server]: Optimizer reset` and `[WARN] [controller_server]: Optimizer fail to compute path` when approaching doorways even while centered.
* **Root Cause:** At `213_map` doorway (`~0.75 m` free opening between occupied cells, `local_costmap` inscribed radius `~0.22 m`, `cost_scaling_factor: 3.0`), inflation cost near center is already `~130` and climbs past `195` within a few cm of either side. Setting `near_collision_cost: 195` caused `CostCritic` to apply `critical_cost: 300.0` across almost the entire doorway width.
* **Fix:** Keep `near_collision_cost: 253` (`INSCRIBED_INFLATED_OBSTACLE`) with `consider_footprint: true` so exact rectangular footprint collision checking resolves tight passages.

### Pitfall 4 — Shrinking `local_costmap.footprint` Removed Corner Safety Buffer
* **Symptom:** Shrinking `local_costmap.footprint` from `[±0.26, ±0.22]` to `[±0.25, ±0.21]` + raising `PathAlignCritic.cost_weight: 8.0` caused physical wall strikes in Gazebo and immediate `"Start occupied"` aborts.
* **Rule:** **Never shrink `local_costmap.footprint` below `[±0.26, ±0.22]`.** Fix path geometry (`SmacPlanner2D.smoother`) and recovery (`bt_navigator` + BT XML), never physical safety margins.

### Pitfall 5 — `bt_navigator.default_server_timeout: 20` Killed Missions Before Recovery
* **Symptom:** Log printed:
  `[ERROR] [bt_navigator_navigate_to_pose_rclcpp_node]: Failed to get result for follow_path in node halt!`
  followed immediately by `Goal failed` — **and `BackUp` never executed**, even though `controller_server` printed `Cancellation was successful. Stopping the robot.` milliseconds later.
* **Root Cause:** `default_server_timeout` was **`20 ms`**, whereas `controller_server` ticks at `10.0 Hz` (**`100 ms`** per cycle). Whenever `FollowPath` needed to be halted to switch to `BackUp`, `BtActionNode::halt()` timed out waiting for cancel confirmation after `20 ms` and aborted the whole behavior tree.
* **Fix:** Set `default_server_timeout: 1000` (`1000 ms`) in [`config/nav2_params.yaml`](config/nav2_params.yaml#L50).

### Pitfall 6 — `WouldAPlannerRecoveryHelp` Does Not Trigger on `START_OCCUPIED (205)`
* **Symptom:** Whenever the robot corner brushed inflation and `SmacPlanner2D` logged `GridBased plugin failed ... "Start occupied"`, the BT skipped recovery and aborted immediately.
* **Root Cause:** In ROS 2 Jazzy (`libnav2_would_a_planner_recovery_help_condition_bt_node.so`), `WouldAPlannerRecoveryHelp` only accepts error codes `UNKNOWN (200)`, `TIMEOUT (207)`, and `NO_VALID_PATH (208)` — **excluding `START_OCCUPIED (205)`**.
* **Fix:** Removed the outer `<WouldAPlannerRecoveryHelp>` / `<WouldAControllerRecoveryHelp>` condition guard before `RecoveryFallback` in both custom BTs so `"Start occupied"` reliably invokes costmap clearing + `BackUp`.

### Pitfall 7 — Tracked Near-Goal Micro-Jerking vs Loose `45°` Finish
* **Symptom:** Because a tracked base has zero lateral velocity (`vy = 0`), arriving `10–20 cm` laterally offset from a goal makes MPPI jitter forward/backward by a few cm if `PreferForwardCritic.threshold_to_consider` (`0.8`) blocks short backing within that radius or `GoalAngleCritic` engages too late (`0.5 m`, weight `3.0`). Conversely, overly loose `xy_goal_tolerance` / `yaw_goal_tolerance` causes the robot to finish `45°` off-heading.
* **Tuning Levers (live-tunable via `ros2 param set`):**
  * Allow small backing closer to goal: lower `FollowPath.PreferForwardCritic.threshold_to_consider` (`0.8` → `0.4`).
  * Start final yaw alignment earlier/stronger: raise `FollowPath.GoalAngleCritic.threshold_to_consider` (`0.5` → `0.7`) and `FollowPath.GoalAngleCritic.cost_weight` (`3.0` → `6.0`).
  * Keep `general_goal_checker.xy_goal_tolerance` (`0.15`–`0.22`) and `yaw_goal_tolerance` (`0.15`–`0.20`) tight enough to avoid `45°` finish poses while testing real track slip.

### Pitfall 8 — `PathAlignCritic` Lookahead & Orientation Alignment
* Setting `offset_from_furthest: 20` on a `15`-step horizon prevented `PathAlignCritic` from engaging reliably at speed (`6` works reliably on `15` steps).
* Setting `use_path_orientations: false` allowed diagonal/sideways entry into doorways; keep `use_path_orientations: true`.
* Remember to run `colcon build --packages-select smart_nav --symlink-install` after adding/changing files in `config/` or `launch/`, otherwise `install/smart_nav/share/smart_nav/` may miss new XML files.

---

## 8. ALARA Radiation Navigation Integration

### 1. Costmap Fusion (`smart_radiation_plugins::RadiationLayer`)
Configured last in `global_costmap.plugins` (`["static_layer", "obstacle_layer", "inflation_layer", "radiation_layer"]`) in [`config/nav2_params.yaml`](config/nav2_params.yaml#L226-L232):
* Subscribes to `/radiation_map` (`nav_msgs/OccupancyGrid`, Transient Local QoS).
* Source logic ([`radiation_layer.cpp`](../smart_radiation_plugins/src/radiation_layer.cpp#L78-L98)):
  1. Never overwrites existing lethal/inscribed obstacles (`if (current_cost >= 253) continue;`).
  2. Converts grid occupancy `rad_value` (`1..100`) to `rad_cost = (rad_value * max_cost_) / 100`.
  3. Writes `final_cost = std::max(current_cost, rad_cost)`.
* **CRITICAL INVARIANT (`max_cost: 220`):** `max_cost` must remain **`< 253`** (`INSCRIBED_INFLATED_OBSTACLE`). With `max_cost: 220` and `SmacPlanner2D.cost_travel_multiplier: 10.0`:
  * Global paths strongly avoid high-dose cells whenever a clean or lower-dose detour exists.
  * If all paths cross radiation (or during `RTH` evacuation from inside a hot zone), the planner still finds a valid escape route instead of throwing `NO_VALID_PATH`.
  * **Do not drastically reduce `cost_travel_multiplier` (`10.0`)** without re-verifying ALARA detour tests!

### 2. Sigmoid Dose Mapping (`radiation_field_server`)
Configured in [`../smart_radiation/config/radiation_params.yaml`](../smart_radiation/config/radiation_params.yaml) and implemented in [`../smart_radiation/smart_radiation/radiation_field_server.py`](../smart_radiation/smart_radiation/radiation_field_server.py#L187-L205):
* `d_noise` (`50.0`): Dose below/at `d_noise` maps to cost **`0`** (sensor noise floor cutoff).
* `d_crit` (`1000.0`): Dose at/above `d_crit` saturates to **`100`** on `/radiation_map` (which becomes **`max_cost = 220`** in `global_costmap`).
* `k` (`10.0`): Sigmoid steepness between `d_noise` and `d_crit` (normalized around midpoint `0.5`). Higher `k` creates a sharper cliff near `0.5 * (d_noise + d_crit)`; lower `k` spreads a gentler gradient across medium dose levels.
* **Dynamic hot-reload:** `/radiation_field_server` implements `add_on_set_parameters_callback` (`param_callback`) and immediately recomputes + republishes `/radiation_map` when `d_noise`, `d_crit`, or `k` changes at runtime.

### 3. ALARA Speed Reflex (`alara_speed_reflex_node`)
Configured in [`../smart_radiation/config/radiation_params.yaml`](../smart_radiation/config/radiation_params.yaml#L18-L22), disabled by default unless launched with `use_alara_reflex:=true` in [`../smart_radiation/launch/radiation_bringup.launch.py`](../smart_radiation/launch/radiation_bringup.launch.py#L75-L79):
* `rad_threshold` (`30.0`): Threshold (`0–100` scale on `/radiation_map`) under robot TF `map -> base_footprint`.
* `normal_speed_pct` (`35.0`) / `boost_speed_pct` (`100.0`): Publishes `/speed_limit` (`percentage: true`) to crawl carefully in clean areas and sprint through contaminated zones (`>= rad_threshold`) to minimize integrated dose.
* **Known Gotcha:** [`alara_speed_reflex.cpp`](../smart_radiation_plugins/src/alara_speed_reflex.cpp#L19-L25) reads `rad_threshold`, `normal_speed_pct`, and `boost_speed_pct` **only once at node startup** (no `add_on_set_parameters_callback`). `ros2 param set` on `/alara_speed_reflex_node` will NOT take effect without restarting the node/session (or adding a parameter callback in C++).

---

## 9. SLAM Toolbox Notes (`slam_lifelong.yaml` & `slam_mapping.yaml`)

* **Frame Chain:** `map -> odom` (published by `slam_toolbox` at `1 / 0.1 = 10 Hz` via `transform_publish_period: 0.1`) and `odom -> base_footprint` (from EKF / Gazebo bridge).
* **`transform_tolerance` / `transform_timeout`:**
  * `slam_toolbox.transform_timeout: 0.8`, `tf_buffer_duration: 30.0`
  * `local_costmap.transform_tolerance: 1.5`
  * `FollowPath.transform_tolerance: 1.0`
  * `collision_monitor.transform_tolerance: 0.2`
  * Keep tolerances relaxed enough (`0.8–1.5 s`) for CPU spikes on Raspberry Pi and Gazebo `use_sim_time` jitter; lowering them to `0.1` causes dropped TF lookups and controller resets.
* **Minimum update thresholds:** `minimum_travel_distance: 0.1` m, `minimum_travel_heading: 0.1` rad, `minimum_time_interval: 0.5` s.

---

## 10. Runtime Tuning & Diagnostics Cheat Sheet

> **Important ROS 2 CLI rule:** All MPPI, goal-checker, and radiation thresholds below are `double` parameters (`Type: double`). Always include a decimal point (e.g., `6.0`, `50.0`, not `6` or `50`), otherwise `ros2 param set` sends `INTEGER` and fails with a type error.

### A. Live MPPI & Goal Tolerance Tuning (`/controller_server`)
```bash
# Test near-goal backing allowance & earlier final yaw alignment:
ros2 param set /controller_server FollowPath.PreferForwardCritic.threshold_to_consider 0.4 && \
ros2 param set /controller_server FollowPath.GoalAngleCritic.threshold_to_consider 0.7 && \
ros2 param set /controller_server FollowPath.GoalAngleCritic.cost_weight 6.0

# Adjust finishing tolerances & stall detection live:
ros2 param set /controller_server general_goal_checker.xy_goal_tolerance 0.20 && \
ros2 param set /controller_server general_goal_checker.yaw_goal_tolerance 0.18 && \
ros2 param set /controller_server progress_checker.movement_time_allowance 4.5

# Inspect all live controller_server parameters:
ros2 param dump /controller_server
```

### B. Live Radiation Threshold Tuning (`/radiation_field_server`)
```bash
# Adjust noise cutoff, critical saturation, and sigmoid slope dynamically:
ros2 param set /radiation_field_server d_noise 50.0 && \
ros2 param set /radiation_field_server d_crit 1000.0 && \
ros2 param set /radiation_field_server k 10.0

# Verify updated radiation map summary in logs or echo header:
ros2 topic echo /radiation_map --once --field info
```

### C. Quick Diagnostic Commands
```bash
# Check Nav2 lifecycle nodes & current active parameters:
ros2 lifecycle get /bt_navigator
ros2 lifecycle get /controller_server
ros2 lifecycle get /planner_server

# Watch live global path, speed limits, and robot status:
ros2 topic echo /speed_limit
ros2 topic echo /nav_status
ros2 topic hz /plan /local_costmap/costmap /global_costmap/costmap

# Rebuild smart_nav cleanly after config/BT edits:
cd ~/ros2_ws && colcon build --packages-select smart_nav --symlink-install
```
