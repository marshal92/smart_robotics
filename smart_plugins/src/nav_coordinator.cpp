#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/string.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <nav2_msgs/action/navigate_to_pose.hpp>
#include <nav2_msgs/action/navigate_through_poses.hpp>
#include <smart_interfaces/msg/smart_command.hpp>
#include <nlohmann/json.hpp>

#include <cmath>
#include <deque>
#include <memory>
#include <string>
#include <vector>
#include <algorithm>
#include <cctype>

using json = nlohmann::json;
using std::placeholders::_1;
using std::placeholders::_2;

struct NavTask {
  std::string type; // "go_to", "waypoints", "rth"
  geometry_msgs::msg::PoseStamped pose;
  std::vector<geometry_msgs::msg::PoseStamped> poses;
  std::vector<int> lap_nums;
  std::string bt;
  int lap{1};
  int total_laps{1};
  std::string name{"point"};
  size_t start_idx{0};
};

struct ResumeSnapshot {
  bool valid{false};
  std::string type; // "waypoints" or "single"
  std::vector<geometry_msgs::msg::PoseStamped> poses;
  std::vector<int> lap_nums;
  int total_laps{1};
  std::string bt;
  std::string name{"route"};
  size_t start_idx{0};
  NavTask single_task;
  std::vector<NavTask> remaining_queue;
};

class NavCoordinatorCpp : public rclcpp::Node {
public:
  using NavigateToPose = nav2_msgs::action::NavigateToPose;
  using GoalHandleToPose = rclcpp_action::ClientGoalHandle<NavigateToPose>;
  using NavigateThroughPoses = nav2_msgs::action::NavigateThroughPoses;
  using GoalHandleThroughPoses = rclcpp_action::ClientGoalHandle<NavigateThroughPoses>;

  NavCoordinatorCpp() : Node("nav_coordinator") {
    cmd_sub_ = this->create_subscription<smart_interfaces::msg::SmartCommand>(
      "/smart_command", 10, std::bind(&NavCoordinatorCpp::cmd_cb, this, _1));
    fsm_sub_ = this->create_subscription<std_msgs::msg::String>(
      "/fsm_status", 10, std::bind(&NavCoordinatorCpp::fsm_cb, this, _1));
    pose_sub_ = this->create_subscription<geometry_msgs::msg::PoseWithCovarianceStamped>(
      "/pose", 5, std::bind(&NavCoordinatorCpp::pose_cb, this, _1));

    status_pub_ = this->create_publisher<std_msgs::msg::String>("/nav_status", 10);

    nav_to_pose_client_ = rclcpp_action::create_client<NavigateToPose>(this, "navigate_to_pose");
    nav_through_poses_client_ = rclcpp_action::create_client<NavigateThroughPoses>(this, "navigate_through_poses");

    // 20 Hz control loop (50 ms) for sliding window advancement and queue dispatch
    control_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(50), std::bind(&NavCoordinatorCpp::control_loop, this));

    // 5 Hz status publication (200 ms)
    status_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(200), std::bind(&NavCoordinatorCpp::publish_status, this));

    RCLCPP_INFO(this->get_logger(), "C++ Nav Coordinator activated (Sliding Window + Zero-Spin Overhead). Awaiting commands.");
  }

private:
  // State variables
  std::deque<NavTask> nav_queue_;
  bool has_active_task_{false};
  NavTask active_task_;
  std::string current_fsm_state_{"UNKNOWN"};
  std::string nav_state_{"IDLE"};
  std::string bt_survival_{""};

  // Sliding Window state
  bool sw_active_{false};
  std::vector<geometry_msgs::msg::PoseStamped> sw_poses_;
  std::vector<int> sw_lap_nums_;
  int sw_total_laps_{1};
  size_t sw_idx_{0};
  std::string sw_bt_{""};
  std::string sw_name_{"route"};
  std::vector<size_t> sw_last_sent_indices_;
  const size_t sw_window_size_{5};
  const double sw_pass_radius_{0.75};
  const double sw_min_end_dist_{1.80};

  ResumeSnapshot resume_snapshot_;
  bool nav_paused_{false};
  bool cancel_requested_{false};

  // Robot pose in map frame
  bool has_robot_pose_{false};
  double robot_x_{0.0};
  double robot_y_{0.0};

  // Route accumulator
  std::vector<geometry_msgs::msg::PoseStamped> route_accumulator_;

  // Goal tracking (generation counter prevents stale result callbacks from overwriting newer goals)
  uint64_t current_goal_id_{0};
  bool goal_in_flight_{false};

  // ROS interfaces
  rclcpp::Subscription<smart_interfaces::msg::SmartCommand>::SharedPtr cmd_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr fsm_sub_;
  rclcpp::Subscription<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr pose_sub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp_action::Client<NavigateToPose>::SharedPtr nav_to_pose_client_;
  rclcpp_action::Client<NavigateThroughPoses>::SharedPtr nav_through_poses_client_;
  rclcpp::TimerBase::SharedPtr control_timer_;
  rclcpp::TimerBase::SharedPtr status_timer_;

  static std::string to_lower_trimmed(const std::string & s) {
    auto start = std::find_if_not(s.begin(), s.end(), [](unsigned char c) { return std::isspace(c); });
    auto end = std::find_if_not(s.rbegin(), s.rend(), [](unsigned char c) { return std::isspace(c); }).base();
    if (start >= end) return "";
    std::string res(start, end);
    std::transform(res.begin(), res.end(), res.begin(), [](unsigned char c) { return std::tolower(c); });
    return res;
  }

  geometry_msgs::msg::PoseStamped create_pose(double x, double y, double yaw) {
    geometry_msgs::msg::PoseStamped p;
    p.header.frame_id = "map";
    p.pose.position.x = x;
    p.pose.position.y = y;
    p.pose.position.z = 0.0;
    p.pose.orientation.x = 0.0;
    p.pose.orientation.y = 0.0;
    p.pose.orientation.z = std::sin(yaw / 2.0);
    p.pose.orientation.w = std::cos(yaw / 2.0);
    return p;
  }

  void pose_cb(const geometry_msgs::msg::PoseWithCovarianceStamped::SharedPtr msg) {
    robot_x_ = msg->pose.pose.position.x;
    robot_y_ = msg->pose.pose.position.y;
    has_robot_pose_ = true;
  }

  void fsm_cb(const std_msgs::msg::String::SharedPtr msg) {
    current_fsm_state_ = msg->data;
  }

  void publish_status() {
    std_msgs::msg::String msg;
    msg.data = nav_state_;
    status_pub_->publish(msg);
  }

  void reset_sliding_window() {
    sw_active_ = false;
    sw_poses_.clear();
    sw_lap_nums_.clear();
    sw_idx_ = 0;
    sw_last_sent_indices_.clear();
  }

  void save_resume_state() {
    if (sw_active_ && !sw_poses_.empty() && sw_idx_ < sw_poses_.size()) {
      resume_snapshot_.valid = true;
      resume_snapshot_.type = "waypoints";
      resume_snapshot_.poses = sw_poses_;
      resume_snapshot_.lap_nums = sw_lap_nums_;
      resume_snapshot_.total_laps = sw_total_laps_;
      resume_snapshot_.bt = sw_bt_;
      resume_snapshot_.name = sw_name_;
      resume_snapshot_.start_idx = sw_idx_;
      resume_snapshot_.remaining_queue.assign(nav_queue_.begin(), nav_queue_.end());
      int cur_lap = (sw_idx_ < sw_lap_nums_.size()) ? sw_lap_nums_[sw_idx_] : sw_total_laps_;
      RCLCPP_INFO(this->get_logger(),
        "[Resume] Saved route '%s' at WP %zu/%zu (Lap %d/%d).",
        sw_name_.c_str(), sw_idx_ + 1, sw_poses_.size(), cur_lap, sw_total_laps_);
    } else if (has_active_task_ && (active_task_.type == "go_to" || active_task_.type == "rth")) {
      resume_snapshot_.valid = true;
      resume_snapshot_.type = "single";
      resume_snapshot_.single_task = active_task_;
      resume_snapshot_.remaining_queue.assign(nav_queue_.begin(), nav_queue_.end());
      RCLCPP_INFO(this->get_logger(),
        "[Resume] Saved point '%s' for resume.", active_task_.name.c_str());
    }
  }

  void build_sliding_window(
    std::vector<geometry_msgs::msg::PoseStamped> & window_poses,
    std::vector<size_t> & indices)
  {
    window_poses.clear();
    indices.clear();
    size_t n = sw_poses_.size();
    if (sw_idx_ >= n) {
      return;
    }

    indices.push_back(sw_idx_);
    for (size_t offset = 1; offset < sw_window_size_; ++offset) {
      size_t cand_idx = sw_idx_ + offset;
      if (cand_idx >= n) {
        break;
      }
      const auto & cand_p = sw_poses_[cand_idx].pose.position;
      const auto & prev_p = sw_poses_[indices.back()].pose.position;
      if (std::hypot(cand_p.x - prev_p.x, cand_p.y - prev_p.y) < 0.25) {
        break;
      }
      if (has_robot_pose_) {
        double dist_to_robot = std::hypot(cand_p.x - robot_x_, cand_p.y - robot_y_);
        if (dist_to_robot < sw_min_end_dist_) {
          break;
        }
      }
      indices.push_back(cand_idx);
    }

    window_poses.reserve(indices.size());
    for (size_t idx : indices) {
      window_poses.push_back(sw_poses_[idx]);
    }
  }

  bool send_sliding_window() {
    std::vector<geometry_msgs::msg::PoseStamped> window_poses;
    std::vector<size_t> indices;
    build_sliding_window(window_poses, indices);
    if (window_poses.empty() || indices == sw_last_sent_indices_) {
      return false;
    }

    auto now_msg = this->now();
    for (auto & p : window_poses) {
      p.header.stamp = now_msg;
    }

    NavigateThroughPoses::Goal goal_msg;
    goal_msg.poses = window_poses;
    goal_msg.behavior_tree = sw_bt_;

    uint64_t goal_id = ++current_goal_id_;
    goal_in_flight_ = true;
    nav_state_ = "MOVING";

    rclcpp_action::Client<NavigateThroughPoses>::SendGoalOptions options;
    options.feedback_callback =
      [this, goal_id](
        GoalHandleThroughPoses::SharedPtr,
        const std::shared_ptr<const NavigateThroughPoses::Feedback> feedback)
      {
        if (goal_id != current_goal_id_ || !feedback) return;
        const auto & cp = feedback->current_pose.pose.position;
        if (cp.x != 0.0 || cp.y != 0.0) {
          robot_x_ = cp.x;
          robot_y_ = cp.y;
          has_robot_pose_ = true;
        }
      };

    options.result_callback =
      [this, goal_id](const GoalHandleThroughPoses::WrappedResult & result) {
        if (goal_id != current_goal_id_) {
          return; // Preempted by a newer window or cancel
        }
        goal_in_flight_ = false;
        handle_action_result(result.code);
      };

    nav_through_poses_client_->async_send_goal(goal_msg, options);
    sw_last_sent_indices_ = indices;

    int cur_lap = (sw_idx_ < sw_lap_nums_.size()) ? sw_lap_nums_[sw_idx_] : sw_total_laps_;
    std::string idx_str = "[";
    for (size_t i = 0; i < indices.size(); ++i) {
      if (i > 0) idx_str += ", ";
      idx_str += std::to_string(indices[i] + 1);
    }
    idx_str += "]";

    RCLCPP_INFO(this->get_logger(),
      "[SlidingWindow] '%s' Lap %d/%d | Window WPs %s/%zu",
      sw_name_.c_str(), cur_lap, sw_total_laps_, idx_str.c_str(), sw_poses_.size());
    return true;
  }

  void send_single_pose_goal(const geometry_msgs::msg::PoseStamped & pose_in, const std::string & bt) {
    NavigateToPose::Goal goal_msg;
    goal_msg.pose = pose_in;
    goal_msg.pose.header.stamp = this->now();
    goal_msg.behavior_tree = bt;

    uint64_t goal_id = ++current_goal_id_;
    goal_in_flight_ = true;
    nav_state_ = "MOVING";

    rclcpp_action::Client<NavigateToPose>::SendGoalOptions options;
    options.feedback_callback =
      [this, goal_id](
        GoalHandleToPose::SharedPtr,
        const std::shared_ptr<const NavigateToPose::Feedback> feedback)
      {
        if (goal_id != current_goal_id_ || !feedback) return;
        const auto & cp = feedback->current_pose.pose.position;
        if (cp.x != 0.0 || cp.y != 0.0) {
          robot_x_ = cp.x;
          robot_y_ = cp.y;
          has_robot_pose_ = true;
        }
      };

    options.result_callback =
      [this, goal_id](const GoalHandleToPose::WrappedResult & result) {
        if (goal_id != current_goal_id_) {
          return;
        }
        goal_in_flight_ = false;
        handle_action_result(result.code);
      };

    nav_to_pose_client_->async_send_goal(goal_msg, options);
  }

  void handle_action_result(rclcpp_action::ResultCode code) {
    if (code == rclcpp_action::ResultCode::SUCCEEDED) {
      if (sw_active_ && !sw_poses_.empty()) {
        size_t last_sent = sw_last_sent_indices_.empty() ? sw_idx_ : sw_last_sent_indices_.back();
        if (last_sent + 1 < sw_poses_.size()) {
          sw_idx_ = last_sent + 1;
          send_sliding_window();
          nav_state_ = "MOVING";
        } else {
          RCLCPP_INFO(this->get_logger(),
            "Route '%s' FINISHED (%zu WPs, %d laps).",
            sw_name_.c_str(), sw_poses_.size(), sw_total_laps_);
          reset_sliding_window();
          nav_state_ = "SUCCEEDED";
        }
      } else {
        nav_state_ = "SUCCEEDED";
      }
    } else if (code == rclcpp_action::ResultCode::CANCELED) {
      reset_sliding_window();
      nav_state_ = "CANCELED";
    } else if (code == rclcpp_action::ResultCode::ABORTED) {
      RCLCPP_WARN(this->get_logger(),
        "Nav2 task ABORTED! State saved — drive away and press RESUME to continue.");
      save_resume_state();
      reset_sliding_window();
      nav_paused_ = true;
      nav_state_ = "ABORTED";
    } else {
      nav_state_ = "IDLE";
    }
  }

  static bool extract_double(const json & j, const std::string & key, double default_val, double & out, bool required = false) {
    if (!j.contains(key)) {
      if (required) return false;
      out = default_val;
      return true;
    }
    const auto & val = j[key];
    try {
      if (val.is_number()) {
        out = val.get<double>();
      } else if (val.is_string()) {
        size_t idx = 0;
        const std::string s = val.get<std::string>();
        out = std::stod(s, &idx);
        if (idx != s.size()) return false;
      } else {
        return false;
      }
    } catch (...) {
      return false;
    }
    return std::isfinite(out);
  }

  static bool extract_int(const json & j, const std::string & key, int default_val, int & out) {
    if (!j.contains(key)) {
      out = default_val;
      return true;
    }
    const auto & val = j[key];
    try {
      if (val.is_number_integer()) {
        out = val.get<int>();
      } else if (val.is_number_float()) {
        double d = val.get<double>();
        if (!std::isfinite(d)) return false;
        out = static_cast<int>(d);
      } else if (val.is_string()) {
        size_t idx = 0;
        const std::string s = val.get<std::string>();
        out = std::stoi(s, &idx);
        if (idx != s.size()) return false;
      } else {
        return false;
      }
    } catch (...) {
      return false;
    }
    return true;
  }

  static bool extract_coord_from_val(const json & val, double & out) {
    try {
      if (val.is_number()) {
        out = val.get<double>();
      } else if (val.is_string()) {
        size_t idx = 0;
        const std::string s = val.get<std::string>();
        out = std::stod(s, &idx);
        if (idx != s.size()) return false;
      } else {
        return false;
      }
    } catch (...) {
      return false;
    }
    return std::isfinite(out);
  }

  void cmd_cb(const smart_interfaces::msg::SmartCommand::SharedPtr msg) {
    const std::string target = to_lower_trimmed(msg->target_system);
    const std::string action = to_lower_trimmed(msg->command);

    // 1. Global system stop commands
    if (target == "system") {
      if (action == "stop" || action == "start_freeride" || action == "restart") {
        RCLCPP_WARN(this->get_logger(), "[System] Navigation disabled globally. Clearing queues.");
        nav_queue_.clear();
        route_accumulator_.clear();
        has_active_task_ = false;
        reset_sliding_window();
        cancel_requested_ = true;
      }
      return;
    }

    if (target != "nav") {
      return;
    }

    if (action == "go_to_named") {
      // Handled by waypoint_manager
      return;
    }

    json payload = json::object();
    if (!msg->payload_json.empty()) {
      try {
        payload = json::parse(msg->payload_json);
      } catch (const std::exception & e) {
        RCLCPP_ERROR(this->get_logger(), "JSON Error in nav:%s: %s", action.c_str(), e.what());
        return;
      }
      if (!payload.is_object()) {
        RCLCPP_ERROR(this->get_logger(), "Expected JSON object in nav:%s", action.c_str());
        return;
      }
    }

    // Cancel
    if (action == "cancel") {
      RCLCPP_INFO(this->get_logger(), "Command CANCEL received. Stopping (state saved for RESUME).");
      save_resume_state();
      nav_queue_.clear();
      reset_sliding_window();
      nav_paused_ = false;
      cancel_requested_ = true;
      has_active_task_ = false;
      return;
    }

    // Resume
    if (action == "resume") {
      if (current_fsm_state_ == "WARNING" || current_fsm_state_ == "EVACUATING") {
        RCLCPP_WARN(this->get_logger(), "Cannot RESUME while safety FSM is in %s.", current_fsm_state_.c_str());
        return;
      }
      if (sw_active_) {
        RCLCPP_INFO(this->get_logger(), "Route is already active.");
        return;
      }
      if (!resume_snapshot_.valid) {
        RCLCPP_WARN(this->get_logger(), "Nothing to resume! Send a route first.");
        return;
      }
      ResumeSnapshot snap = resume_snapshot_;
      resume_snapshot_.valid = false;
      nav_paused_ = false;
      nav_queue_.clear();

      if (snap.type == "waypoints") {
        NavTask resume_task;
        resume_task.type = "waypoints";
        resume_task.poses = snap.poses;
        resume_task.lap_nums = snap.lap_nums;
        resume_task.bt = snap.bt;
        resume_task.total_laps = snap.total_laps;
        resume_task.name = snap.name;
        resume_task.start_idx = snap.start_idx;

        active_task_ = resume_task;
        has_active_task_ = true;
        nav_queue_.push_back(resume_task);
        for (const auto & rem : snap.remaining_queue) {
          nav_queue_.push_back(rem);
        }
        int cur_lap = (snap.start_idx < snap.lap_nums.size()) ? snap.lap_nums[snap.start_idx] : snap.total_laps;
        RCLCPP_INFO(this->get_logger(),
          "Command RESUME: continuing '%s' from WP %zu/%zu (Lap %d/%d).",
          resume_task.name.c_str(), snap.start_idx + 1, snap.poses.size(), cur_lap, resume_task.total_laps);
      } else if (snap.type == "single") {
        active_task_ = snap.single_task;
        has_active_task_ = true;
        nav_queue_.push_back(snap.single_task);
        for (const auto & rem : snap.remaining_queue) {
          nav_queue_.push_back(rem);
        }
        RCLCPP_INFO(this->get_logger(),
          "Command RESUME: continuing point '%s'.", snap.single_task.name.c_str());
      }
      return;
    }

    // RTH
    if (action == "rth") {
      double rx = 0.0, ry = 0.0, ryaw = 0.0;
      if (!extract_double(payload, "x", 0.0, rx) ||
          !extract_double(payload, "y", 0.0, ry) ||
          !extract_double(payload, "yaw", 0.0, ryaw))
      {
        RCLCPP_ERROR(this->get_logger(), "Invalid or non-finite RTH coordinates.");
        return;
      }
      RCLCPP_INFO(this->get_logger(), "Command RTH received. Returning to base!");
      NavTask rth_task;
      rth_task.type = "rth";
      rth_task.name = "rth";
      rth_task.pose = create_pose(rx, ry, ryaw);

      nav_queue_.clear();
      reset_sliding_window();
      nav_paused_ = false;
      cancel_requested_ = true;
      nav_queue_.push_back(rth_task);
      return;
    }

    // Safety FSM check for regular movement commands
    if (current_fsm_state_ != "NORMAL" && current_fsm_state_ != "DISABLED") {
      RCLCPP_WARN(this->get_logger(),
        "Restricted: system in state %s. Route rejected.", current_fsm_state_.c_str());
      return;
    }

    // Single point go_to
    if (action == "go_to" || action == "go_to_with_bt") {
      double gx = 0.0, gy = 0.0, gyaw = 0.0;
      int laps = 1;
      if (!extract_double(payload, "x", 0.0, gx, true) ||
          !extract_double(payload, "y", 0.0, gy, true) ||
          !extract_double(payload, "yaw", 0.0, gyaw, false) ||
          !extract_int(payload, "laps", 1, laps))
      {
        RCLCPP_ERROR(this->get_logger(), "Invalid or missing parameters in nav:%s", action.c_str());
        return;
      }
      laps = std::clamp(laps, 1, 100);
      std::string name = payload.contains("name") && payload["name"].is_string() ? payload["name"].get<std::string>() : "point";
      std::string bt = payload.contains("bt") && payload["bt"].is_string() ? payload["bt"].get<std::string>() : "";

      nav_paused_ = false;
      for (int lap = 1; lap <= laps; ++lap) {
        NavTask task;
        task.type = "go_to";
        task.pose = create_pose(gx, gy, gyaw);
        task.bt = bt;
        task.lap = lap;
        task.total_laps = laps;
        task.name = name;
        active_task_ = task;
        has_active_task_ = true;
        nav_queue_.push_back(task);
      }
      RCLCPP_INFO(this->get_logger(),
        "Queued point '%s' (laps=%d). Queue size: %zu", name.c_str(), laps, nav_queue_.size());
    }
    // Multi-point route
    else if (action == "waypoints" || action == "patrol" || action == "follow_route") {
      if (!payload.contains("points") || !payload["points"].is_array()) {
        RCLCPP_ERROR(this->get_logger(), "Missing or invalid 'points' array in nav:%s", action.c_str());
        return;
      }
      const auto & pts = payload["points"];
      if (pts.empty() || pts.size() > 500) {
        RCLCPP_ERROR(this->get_logger(), "Empty or oversized 'points' list (%zu) in nav:%s", pts.size(), action.c_str());
        return;
      }
      int laps = 1;
      if (!extract_int(payload, "laps", 1, laps)) {
        RCLCPP_ERROR(this->get_logger(), "Invalid 'laps' in nav:%s", action.c_str());
        return;
      }
      laps = std::clamp(laps, 1, 100);

      struct RawPt { double x; double y; double yaw; };
      std::vector<RawPt> parsed_pts;
      parsed_pts.reserve(pts.size());
      for (const auto & p : pts) {
        if (!p.is_array() || p.size() < 2) {
          RCLCPP_ERROR(this->get_logger(), "Malformed waypoint entry in nav:%s", action.c_str());
          return;
        }
        double px = 0.0, py = 0.0, pyaw = 0.0;
        if (!extract_coord_from_val(p[0], px) || !extract_coord_from_val(p[1], py)) {
          RCLCPP_ERROR(this->get_logger(), "Invalid waypoint coordinates in nav:%s", action.c_str());
          return;
        }
        if (p.size() > 2 && !extract_coord_from_val(p[2], pyaw)) {
          RCLCPP_ERROR(this->get_logger(), "Invalid waypoint yaw in nav:%s", action.c_str());
          return;
        }
        parsed_pts.push_back({px, py, pyaw});
      }

      nav_paused_ = false;
      std::string name = payload.contains("name") && payload["name"].is_string() ? payload["name"].get<std::string>() : "route";
      std::string bt = payload.contains("bt") && payload["bt"].is_string() ? payload["bt"].get<std::string>() : "";

      std::vector<geometry_msgs::msg::PoseStamped> all_poses;
      std::vector<int> lap_nums;
      for (int lap = 1; lap <= laps; ++lap) {
        for (const auto & pt : parsed_pts) {
          auto pose = create_pose(pt.x, pt.y, pt.yaw);
          if (!all_poses.empty()) {
            const auto & prev = all_poses.back().pose.position;
            const auto & cur = pose.pose.position;
            if (std::hypot(cur.x - prev.x, cur.y - prev.y) < 0.20) {
              continue;
            }
          }
          all_poses.push_back(pose);
          lap_nums.push_back(lap);
        }
      }

      NavTask task;
      task.type = "waypoints";
      task.poses = all_poses;
      task.lap_nums = lap_nums;
      task.bt = bt;
      task.total_laps = laps;
      task.name = name;
      task.start_idx = 0;

      active_task_ = task;
      has_active_task_ = true;
      nav_queue_.push_back(task);
      RCLCPP_INFO(this->get_logger(),
        "Queued route '%s' (%zu pts x %d laps -> %zu waypoints). Queue size: %zu",
        name.c_str(), parsed_pts.size(), laps, all_poses.size(), nav_queue_.size());
    }
    // Add one point to accumulator
    else if (action == "add_to_route") {
      double px = 0.0, py = 0.0, pyaw = 0.0;
      if (!extract_double(payload, "x", 0.0, px, true) ||
          !extract_double(payload, "y", 0.0, py, true) ||
          !extract_double(payload, "yaw", 0.0, pyaw, false))
      {
        RCLCPP_ERROR(this->get_logger(), "Invalid or missing coordinates in add_to_route");
        return;
      }
      route_accumulator_.push_back(create_pose(px, py, pyaw));
      RCLCPP_INFO(this->get_logger(),
        "Point added to route. Total points in queue: %zu", route_accumulator_.size());
    }
    // Start accumulated route
    else if (action == "start_route") {
      if (route_accumulator_.empty()) {
        RCLCPP_WARN(this->get_logger(), "Route is empty! Add points first.");
        return;
      }
      NavTask task;
      task.type = "waypoints";
      task.poses = route_accumulator_;
      task.lap_nums.assign(route_accumulator_.size(), 1);
      task.bt = payload.contains("bt") && payload["bt"].is_string() ? payload["bt"].get<std::string>() : "";
      task.total_laps = 1;
      task.name = "accumulated_route";
      task.start_idx = 0;

      active_task_ = task;
      has_active_task_ = true;
      nav_queue_.push_back(task);
      RCLCPP_INFO(this->get_logger(),
        "Starting accumulated route with %zu points.", route_accumulator_.size());
      route_accumulator_.clear();
    }
    // Clear accumulated route
    else if (action == "clear_route") {
      route_accumulator_.clear();
      RCLCPP_INFO(this->get_logger(), "Accumulated route cleared.");
    }
  }

  void control_loop() {
    // 1. Handle pending cancel immediately
    if (cancel_requested_) {
      cancel_requested_ = false;
      reset_sliding_window();
      current_goal_id_++; // Invalidate any in-flight goal callbacks
      if (goal_in_flight_ || nav_state_ == "MOVING") {
        nav_to_pose_client_->async_cancel_all_goals();
        nav_through_poses_client_->async_cancel_all_goals();
      }
      goal_in_flight_ = false;
      nav_state_ = "CANCELED";
      if (nav_queue_.empty()) {
        has_active_task_ = false;
      }
    }

    // 2. Advance Sliding Window based on current robot position
    if (sw_active_ && !sw_poses_.empty() && has_robot_pose_) {
      if (sw_idx_ + 1 < sw_poses_.size()) {
        bool advanced = false;
        while (sw_idx_ + 1 < sw_poses_.size()) {
          const auto & target_p = sw_poses_[sw_idx_].pose.position;
          double dist = std::hypot(target_p.x - robot_x_, target_p.y - robot_y_);
          if (dist <= sw_pass_radius_) {
            sw_idx_++;
            advanced = true;
          } else {
            break;
          }
        }
        if (advanced) {
          send_sliding_window();
        }
      }
    }

    // 3. Dispatch next queued task when idle
    if (nav_queue_.empty()) {
      return;
    }
    if (goal_in_flight_ || nav_state_ == "MOVING" || sw_active_ || nav_paused_) {
      return;
    }

    const std::string & next_cmd = nav_queue_.front().type;
    if (next_cmd != "rth" &&
        current_fsm_state_ != "NORMAL" &&
        current_fsm_state_ != "DISABLED" &&
        current_fsm_state_ != "UNKNOWN")
    {
      return;
    }

    // Non-blocking check for Nav2 action server availability
    if (!nav_to_pose_client_->action_server_is_ready()) {
      RCLCPP_WARN_THROTTLE(
        this->get_logger(), *this->get_clock(), 5000, "Nav2 deactivated. Waiting...");
      return;
    }

    NavTask task = nav_queue_.front();
    nav_queue_.pop_front();
    active_task_ = task;
    has_active_task_ = true;

    std::string lap_info = (task.total_laps > 1)
      ? (" [Lap " + std::to_string(task.lap) + "/" + std::to_string(task.total_laps) + "]")
      : "";
    RCLCPP_INFO(this->get_logger(),
      "Starting task '%s'%s. Remaining in queue: %zu",
      task.name.c_str(), lap_info.c_str(), nav_queue_.size());

    if (task.type == "go_to") {
      send_single_pose_goal(task.pose, task.bt);
    } else if (task.type == "waypoints") {
      if (task.poses.empty()) {
        return;
      }
      sw_active_ = true;
      sw_poses_ = task.poses;
      sw_lap_nums_ = task.lap_nums.empty() ? std::vector<int>(task.poses.size(), 1) : task.lap_nums;
      sw_total_laps_ = task.total_laps;
      sw_bt_ = task.bt;
      sw_name_ = task.name;
      sw_idx_ = task.start_idx;
      sw_last_sent_indices_.clear();

      if (sw_idx_ == 0 && has_robot_pose_ && sw_poses_.size() > 1) {
        const auto & p0 = sw_poses_[0].pose.position;
        double d0 = std::hypot(p0.x - robot_x_, p0.y - robot_y_);
        if (d0 < 0.65) {
          sw_idx_ = 1;
          RCLCPP_INFO(this->get_logger(),
            "[SlidingWindow] Robot already at WP 1 (d=%.2fm), starting from WP 2/%zu",
            d0, sw_poses_.size());
        }
      }
      send_sliding_window();
    } else if (task.type == "rth") {
      send_single_pose_goal(task.pose, bt_survival_);
    }
  }
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<NavCoordinatorCpp>());
  rclcpp::shutdown();
  return 0;
}
