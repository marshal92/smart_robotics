import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    pkg_smart_nav = FindPackageShare('smart_nav')
    pkg_nav2_bringup = FindPackageShare('nav2_bringup')

    map_name_arg = DeclareLaunchArgument('map_name', default_value='213_map')
    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='true')
    use_sim_time = LaunchConfiguration('use_sim_time')

    slam_lifelong_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_smart_nav, 'launch', 'slam_lifelong.launch.py'])),
        launch_arguments={'use_sim_time': use_sim_time, 'map_name': LaunchConfiguration('map_name')}.items()
    )

    nav2_config_path = PathJoinSubstitution([pkg_smart_nav, 'config', 'nav2_params.yaml'])
    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_nav2_bringup, 'launch', 'navigation_launch.py'])),
        launch_arguments={'use_sim_time': use_sim_time, 'params_file': nav2_config_path}.items()
    )

    return LaunchDescription([
        map_name_arg, use_sim_time_arg,
        slam_lifelong_launch,
        TimerAction(period=3.0, actions=[nav2_launch])
    ])