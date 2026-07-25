import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    pkg_smart_nav = FindPackageShare('smart_nav')
    pkg_slam_toolbox = FindPackageShare('slam_toolbox')

    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='true')

    slam_config_path = PathJoinSubstitution([pkg_smart_nav, 'config', 'slam_mapping.yaml'])

    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_slam_toolbox, 'launch', 'online_async_launch.py'])),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'slam_params_file': slam_config_path
        }.items()
    )

    return LaunchDescription([
        use_sim_time_arg,
        slam_launch
    ])