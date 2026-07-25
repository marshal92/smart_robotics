#include "smart_plugins/radiation_layer.hpp"
#include "nav2_costmap_2d/costmap_math.hpp"
#include "pluginlib/class_list_macros.hpp"
#include <algorithm>

PLUGINLIB_EXPORT_CLASS(smart_plugins::RadiationLayer, nav2_costmap_2d::Layer)

namespace smart_plugins
{

RadiationLayer::RadiationLayer() : need_bounds_update_(false), enabled_(false) {}

void RadiationLayer::onInitialize()
{
  auto node = node_.lock(); 
  if (!node) throw std::runtime_error("Failed to lock node");

  declareParameter("radiation_topic", rclcpp::ParameterValue("/radiation_map"));
  std::string topic = node->get_parameter(name_ + ".radiation_topic").as_string();
  
  rad_map_sub_ = node->create_subscription<nav_msgs::msg::OccupancyGrid>(
    topic, rclcpp::QoS(1).transient_local(),
    std::bind(&RadiationLayer::mapCallback, this, std::placeholders::_1));

  current_ = true;
  enabled_ = true;
  RCLCPP_INFO(node->get_logger(), "===> RadiationLayer (STABLE: Max Superposition) Initialized!");
}

void RadiationLayer::mapCallback(const nav_msgs::msg::OccupancyGrid::SharedPtr msg)
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  latest_rad_map_ = msg;
  need_bounds_update_ = true;
}

void RadiationLayer::updateBounds(
  double /*robot_x*/, double /*robot_y*/, double /*robot_yaw*/,
  double * min_x, double * min_y, double * max_x, double * max_y)
{
  if (!enabled_ || !latest_rad_map_) return;

  std::lock_guard<std::mutex> lock(data_mutex_);
  if (need_bounds_update_) {
    double map_min_x = latest_rad_map_->info.origin.position.x;
    double map_min_y = latest_rad_map_->info.origin.position.y;
    double map_max_x = map_min_x + (latest_rad_map_->info.width * latest_rad_map_->info.resolution);
    double map_max_y = map_min_y + (latest_rad_map_->info.height * latest_rad_map_->info.resolution);

    *min_x = std::min(*min_x, map_min_x);
    *min_y = std::min(*min_y, map_min_y);
    *max_x = std::max(*max_x, map_max_x);
    *max_y = std::max(*max_y, map_max_y);
    
    need_bounds_update_ = false;
  }
}

void RadiationLayer::updateCosts(
  nav2_costmap_2d::Costmap2D & master_grid,
  int min_i, int min_j, int max_i, int max_j)
{
  if (!enabled_ || !latest_rad_map_) return;

  std::lock_guard<std::mutex> lock(data_mutex_);
  
  double res = latest_rad_map_->info.resolution;
  double ox = latest_rad_map_->info.origin.position.x;
  double oy = latest_rad_map_->info.origin.position.y;
  int width = latest_rad_map_->info.width;
  int height = latest_rad_map_->info.height;

  for (int j = min_j; j < max_j; j++) {
    for (int i = min_i; i < max_i; i++) {
      
      unsigned char current_cost = master_grid.getCost(i, j);
      
      if (current_cost >= 253) continue;

      double wx, wy;
      master_grid.mapToWorld(i, j, wx, wy);
      
      int rad_x = static_cast<int>((wx - ox) / res);
      int rad_y = static_cast<int>((wy - oy) / res);

      if (rad_x < 0 || rad_x >= width || rad_y < 0 || rad_y >= height) continue;

      int8_t rad_value = latest_rad_map_->data[rad_y * width + rad_x];
      if (rad_value <= 0) continue;

      unsigned char rad_cost = static_cast<unsigned char>((rad_value * 252) / 100);

      unsigned char final_cost = std::max(current_cost, rad_cost);
      
      master_grid.setCost(i, j, final_cost);
    }
  }
}

void RadiationLayer::reset()
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  current_ = false;
  need_bounds_update_ = true;
}

} // namespace smart_plugins