cmake_minimum_required(VERSION 3.8)
project(smart_radiation_plugins)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(nav2_costmap_2d REQUIRED)
find_package(nav2_core REQUIRED)
find_package(pluginlib REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(nav2_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(std_srvs REQUIRED)

add_library(smart_radiation_layer SHARED
  src/radiation_layer.cpp
)

target_include_directories(smart_radiation_layer PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(smart_radiation_layer
  rclcpp
  nav2_costmap_2d
  nav2_core
  pluginlib
  std_msgs
  geometry_msgs
  nav_msgs
)

pluginlib_export_plugin_description_file(nav2_costmap_2d plugins.xml)

add_executable(radiation_mapper_node src/radiation_mapper_node.cpp)
ament_target_dependencies(radiation_mapper_node
  rclcpp
  std_msgs
  std_srvs
  tf2_ros
  geometry_msgs
  nlohmann_json
)

add_executable(virtual_geiger_node src/virtual_geiger_node.cpp)
ament_target_dependencies(virtual_geiger_node
  rclcpp
  std_msgs
  tf2_ros
  geometry_msgs
  nlohmann_json
)

add_executable(alara_speed_reflex_node src/alara_speed_reflex.cpp)
ament_target_dependencies(alara_speed_reflex_node
  rclcpp
  nav_msgs
  nav2_msgs
  tf2_ros
  geometry_msgs
)

install(TARGETS smart_radiation_layer radiation_mapper_node virtual_geiger_node alara_speed_reflex_node
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/ DESTINATION include)
install(FILES plugins.xml DESTINATION share/${PROJECT_NAME})

ament_export_include_directories(include)
ament_export_libraries(smart_radiation_layer)
ament_export_dependencies(rclcpp nav2_costmap_2d nav2_core pluginlib std_msgs geometry_msgs nav_msgs)
ament_package()
