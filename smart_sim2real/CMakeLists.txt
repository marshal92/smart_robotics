cmake_minimum_required(VERSION 3.5)
project(smart_sim2real)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch urdf worlds config
  DESTINATION share/${PROJECT_NAME}
)

ament_environment_hooks("hooks/gz_sim_resource_path.dsv")

ament_package()