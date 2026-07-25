cmake_minimum_required(VERSION 3.5)
project(smart_nav)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY config launch maps behavior_trees
  DESTINATION share/${PROJECT_NAME}
)

ament_package()