#ifndef SMART_PLUGINS__RADIATION_LAYER_HPP_
#define SMART_PLUGINS__RADIATION_LAYER_HPP_

#include "rclcpp/rclcpp.hpp"
#include "nav2_costmap_2d/layer.hpp"
#include "nav2_costmap_2d/layered_costmap.hpp"
#include "nav_msgs/msg/occupancy_grid.hpp"
#include <mutex>

namespace smart_plugins
{

class RadiationLayer : public nav2_costmap_2d::Layer
{
public:
  RadiationLayer();
  virtual ~RadiationLayer() = default;

  virtual void onInitialize() override;
  virtual void updateBounds(
    double robot_x, double robot_y, double robot_yaw,
    double * min_x, double * min_y, double * max_x, double * max_y) override;
  virtual void updateCosts(
    nav2_costmap_2d::Costmap2D & master_grid,
    int min_i, int min_j, int max_i, int max_j) override;
  virtual void reset() override;
  virtual bool isClearable() override {return false;}

private:
  void mapCallback(const nav_msgs::msg::OccupancyGrid::SharedPtr msg);

  rclcpp::Subscription<nav_msgs::msg::OccupancyGrid>::SharedPtr rad_map_sub_;
  nav_msgs::msg::OccupancyGrid::SharedPtr latest_rad_map_;
  
  std::mutex data_mutex_;
  bool need_bounds_update_;
  bool enabled_;
};

}  // namespace smart_plugins

#endif