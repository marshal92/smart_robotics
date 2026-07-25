cmake_minimum_required(VERSION 3.5)
project(smart_sim2real)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch urdf worlds models config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()