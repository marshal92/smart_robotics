#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"
#include "sensor_msgs/point_cloud2_iterator.hpp"
#include "tf2_ros/buffer.h"
#include "tf2_ros/transform_listener.h"
#include "tf2_ros/transform_broadcaster.h"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"
#include "tf2/LinearMath/Transform.h"
#include "tf2/utils.h"

using namespace std::chrono_literals;

namespace {
struct LowProfilePoint {
  double range;
  double z;
  unsigned bin;
};
}

class StabilizedFramePublisher : public rclcpp::Node {
public:
  StabilizedFramePublisher() : Node("stabilized_frame_publisher") {
    odom_frame_ = declare_parameter<std::string>("odom_frame", "odom");
    base_frame_ = declare_parameter<std::string>("base_frame", "base_footprint");
    target_frame_ = declare_parameter<std::string>("target_frame", "base_stabilized");
    stabilize_ = declare_parameter<bool>("stabilize", true);

    // Main scan slice (0.30m to 0.80m)
    min_height_ = declare_parameter<double>("min_height", 0.30);
    max_height_ = declare_parameter<double>("max_height", 0.80);
    range_min_ = declare_parameter<double>("range_min", 0.15);
    range_max_ = declare_parameter<double>("range_max", 10.0);
    tf_tolerance_ = declare_parameter<double>("transform_tolerance", 0.05);

    // Robot self-mask (half-length X and half-width Y around base center)
    mask_x_ = declare_parameter<double>("robot_mask_x", 0.35);
    mask_y_ = declare_parameter<double>("robot_mask_y", 0.28);

    // Sharp low-step filter (0.10m to 0.30m)
    add_low_obstacles_ = declare_parameter<bool>("add_low_obstacles", true);
    low_min_height_ = declare_parameter<double>("low_min_height", 0.10);    // 10 cm
    low_max_height_ = declare_parameter<double>("low_max_height", 0.30);    // 30 cm (meets main slice)
    min_step_height_ = declare_parameter<double>("min_step_height", 0.09);  // 9 cm sharp jump
    max_slope_deg_ = declare_parameter<double>("max_slope_deg", 38.0);      // only jumps steeper than 38 deg
    steep_slope_thresh_ = std::tan(max_slope_deg_ * M_PI / 180.0);          // ~0.78

    bins_ = 720;
    angle_min_ = -static_cast<float>(M_PI);
    angle_max_ = static_cast<float>(M_PI);
    angle_increment_ = 2.0f * static_cast<float>(M_PI) / static_cast<float>(bins_);

    sectors_ = 360;
    sector_step_ = 2.0 * M_PI / static_cast<double>(sectors_);

    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
    tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);
    tf_broadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(this);

    // 1. TF Broadcaster Timer: ALWAYS runs at 50Hz
    timer_ = create_wall_timer(20ms, [this]() {
      try {
        auto t = tf_buffer_->lookupTransform(odom_frame_, base_frame_, tf2::TimePointZero);
        if (stabilize_) {
          publishLevelFrame(t);
        }
      } catch (const tf2::TransformException &) {}
    });

    // 2. Scan Publisher & PointCloud Subscriber
    scan_pub_ = create_publisher<sensor_msgs::msg::LaserScan>("/scan", rclcpp::QoS(10));
    cloud_sub_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      "/points", rclcpp::SensorDataQoS(),
      std::bind(&StabilizedFramePublisher::cloudCallback, this, std::placeholders::_1));

    RCLCPP_INFO(get_logger(),
      "⚖️ Stabilized Frame Publisher & Scan Generator started (slice=[%.2f..%.2fm], low_steps=[%.2f..%.2fm], mask=[%.2fx%.2fm])",
      min_height_, max_height_, low_min_height_, low_max_height_, mask_x_ * 2.0, mask_y_ * 2.0);
  }

private:
  tf2::Transform publishLevelFrame(geometry_msgs::msg::TransformStamped t) {
    tf2::Quaternion q;
    q.setRPY(0.0, 0.0, tf2::getYaw(t.transform.rotation));
    t.child_frame_id = target_frame_;
    t.transform.rotation = tf2::toMsg(q);
    tf_broadcaster_->sendTransform(t);
    tf2::Transform result;
    tf2::fromMsg(t.transform, result);
    return result;
  }

  void cloudCallback(const sensor_msgs::msg::PointCloud2::ConstSharedPtr msg) {
    try {
      if (msg->width == 0 || msg->height == 0 || msg->data.empty()) return;

      const rclcpp::Time stamp(msg->header.stamp, get_clock()->get_clock_type());
      const rclcpp::Duration timeout = rclcpp::Duration::from_seconds(tf_tolerance_);

      auto pose = tf_buffer_->lookupTransform(odom_frame_, base_frame_, stamp, timeout);
      auto source = tf_buffer_->lookupTransform(odom_frame_, msg->header.frame_id, stamp, timeout);
      tf2::Transform source_tf;
      tf2::fromMsg(source.transform, source_tf);

      tf2::Transform transform;
      std::string scan_frame;
      if (stabilize_) {
        transform = publishLevelFrame(pose).inverse() * source_tf;
        scan_frame = target_frame_;
      } else {
        tf2::Transform base_tf;
        tf2::fromMsg(pose.transform, base_tf);
        transform = base_tf.inverse() * source_tf;
        scan_frame = base_frame_;
      }

      sensor_msgs::msg::LaserScan scan;
      scan.header = msg->header;
      scan.header.frame_id = scan_frame;
      scan.angle_min = angle_min_;
      scan.angle_max = angle_max_;
      scan.angle_increment = angle_increment_;
      scan.time_increment = 0.0f;
      scan.scan_time = 0.1f;
      scan.range_min = static_cast<float>(range_min_);
      scan.range_max = static_cast<float>(range_max_);

      scan.ranges.assign(bins_, std::numeric_limits<float>::infinity());

      std::vector<std::vector<LowProfilePoint>> profiles;
      if (add_low_obstacles_) {
        profiles.resize(sectors_);
      }

      sensor_msgs::PointCloud2ConstIterator<float> x(*msg, "x"), y(*msg, "y"), z(*msg, "z");
      for (; x != x.end(); ++x, ++y, ++z) {
        if (!std::isfinite(*x) || !std::isfinite(*y) || !std::isfinite(*z)) continue;

        const auto p = transform * tf2::Vector3(*x, *y, *z);

        // Tank body/tracks self-mask: completely ignore points inside the robot footprint
        if (std::abs(p.x()) < mask_x_ && std::abs(p.y()) < mask_y_) continue;

        const double r = std::hypot(p.x(), p.y());
        if (r < range_min_ || r > range_max_) continue;

        double a = std::atan2(p.y(), p.x()) + M_PI;
        if (a < 0.0) a = 0.0;
        const unsigned bin = std::min(bins_ - 1, static_cast<unsigned>(a / angle_increment_));

        // 1. Standard obstacle slice (0.30m to 0.80m)
        if (p.z() >= min_height_ && p.z() <= max_height_) {
          if (!std::isfinite(scan.ranges[bin]) || r < scan.ranges[bin]) {
            scan.ranges[bin] = static_cast<float>(r);
          }
        }

        // 2. Collect points for near-field step gradient analysis (within 3.2m)
        if (add_low_obstacles_ && p.z() >= -0.10 && p.z() <= low_max_height_ && r <= 3.2) {
          const unsigned sector = std::min(sectors_ - 1, static_cast<unsigned>(a / sector_step_));
          profiles[sector].push_back({r, p.z(), bin});
        }
      }

      // Strict local-gradient step detector
      if (add_low_obstacles_) {
        std::vector<float> low_candidates(bins_, std::numeric_limits<float>::infinity());

        for (auto & profile : profiles) {
          if (profile.size() < 2) continue;
          std::sort(profile.begin(), profile.end(),
            [](const LowProfilePoint & a, const LowProfilePoint & b) {
              return a.range == b.range ? a.z < b.z : a.range < b.range;
            });

          double ref_r = profile[0].range;
          double ref_z = profile[0].z;

          for (size_t i = 1; i < profile.size(); ++i) {
            const auto & pt = profile[i];
            const double dr = pt.range - ref_r;
            const double dz = pt.z - ref_z;

            // Only compare closely spaced rings (<= 0.35m)
            if (dr > 0.35) {
              ref_r = pt.range;
              ref_z = pt.z;
              continue;
            }

            // Sharp vertical wall (dr < 0.04m, dz >= 0.09m) or very steep step (> 38 deg, dz >= 0.09m)
            const bool is_vertical_wall = (dr < 0.04 && dz >= min_step_height_);
            const bool is_steep_step = (dr >= 0.04 && dz >= min_step_height_ && (dz / dr) > steep_slope_thresh_);

            if (is_vertical_wall || is_steep_step) {
              if (pt.z >= low_min_height_ && pt.z <= low_max_height_) {
                if (!std::isfinite(low_candidates[pt.bin]) || pt.range < low_candidates[pt.bin]) {
                  low_candidates[pt.bin] = static_cast<float>(pt.range);
                }
              }
              continue;
            }

            if (dr >= 0.03) {
              ref_r = pt.range;
              ref_z = pt.z;
            }
          }
        }

        // Strict 3-bin contiguous cluster filter: eliminates isolated 1-bin and 2-bin terrain noise
        for (unsigned i = 0; i < bins_; ++i) {
          if (!std::isfinite(low_candidates[i])) continue;
          const unsigned prev = (i == 0) ? (bins_ - 1) : (i - 1);
          const unsigned next = (i + 1 == bins_) ? 0 : (i + 1);
          const unsigned prev2 = (prev == 0) ? (bins_ - 1) : (prev - 1);
          const unsigned next2 = (next + 1 == bins_) ? 0 : (next + 1);

          auto close_to = [&](unsigned idx) {
            return std::isfinite(low_candidates[idx]) &&
                   std::abs(low_candidates[idx] - low_candidates[i]) < 0.18f;
          };

          // Must be part of a >= 3-bin continuous arc (center of 3, left of 3, or right of 3)
          const bool cluster_of_3 =
            (close_to(prev) && close_to(next)) ||
            (close_to(prev) && close_to(prev2)) ||
            (close_to(next) && close_to(next2));

          if (cluster_of_3) {
            if (!std::isfinite(scan.ranges[i]) || low_candidates[i] < scan.ranges[i]) {
              scan.ranges[i] = low_candidates[i];
            }
          }
        }
      }

      scan_pub_->publish(scan);

    } catch (const std::exception & e) {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 3000, "Scan skipped: %s", e.what());
    }
  }

  std::string odom_frame_, base_frame_, target_frame_;
  bool stabilize_{true};
  double min_height_{0.30}, max_height_{0.80}, range_min_{0.15}, range_max_{10.0}, tf_tolerance_{0.05};
  double mask_x_{0.35}, mask_y_{0.28};
  bool add_low_obstacles_{true};
  double low_min_height_{0.10}, low_max_height_{0.30}, min_step_height_{0.09}, max_slope_deg_{38.0}, steep_slope_thresh_{0.78};
  unsigned bins_{720}, sectors_{360};
  float angle_min_, angle_max_, angle_increment_;
  double sector_step_;

  std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
  std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
  std::shared_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Publisher<sensor_msgs::msg::LaserScan>::SharedPtr scan_pub_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr cloud_sub_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<StabilizedFramePublisher>());
  rclcpp::shutdown();
  return 0;
}
