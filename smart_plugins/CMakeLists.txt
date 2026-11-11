cmake_minimum_required(VERSION 3.8)
project(smart_plugins)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(nav2_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(control_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(smart_interfaces REQUIRED)
find_package(nlohmann_json REQUIRED)

add_executable(stabilized_frame_publisher_node src/stabilized_frame_publisher.cpp)
ament_target_dependencies(stabilized_frame_publisher_node
  rclcpp
  sensor_msgs
  tf2
  tf2_ros
  geometry_msgs
  tf2_geometry_msgs
)

add_executable(telemetry_mux src/telemetry_mux.cpp)
ament_target_dependencies(telemetry_mux 
  rclcpp 
  std_msgs 
  nav_msgs 
  smart_interfaces 
  nlohmann_json
)

add_executable(nav_coordinator src/nav_coordinator.cpp)
ament_target_dependencies(nav_coordinator
  rclcpp
  rclcpp_action
  std_msgs
  geometry_msgs
  nav2_msgs
  smart_interfaces
  nlohmann_json
)

add_executable(trajectory_bridge src/trajectory_bridge.cpp)
ament_target_dependencies(trajectory_bridge
  rclcpp
  rclcpp_action
  std_msgs
  sensor_msgs
  trajectory_msgs
  control_msgs
)

install(TARGETS stabilized_frame_publisher_node telemetry_mux nav_coordinator trajectory_bridge
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

ament_package()
