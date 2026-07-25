import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from nav2_common.launch import RewrittenYaml

def generate_launch_description():
    pkg_smart_nav = FindPackageShare('smart_nav')
    pkg_slam_toolbox = FindPackageShare('slam_toolbox')

    map_name_arg = DeclareLaunchArgument('map_name', default_value='213_map')
    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='true')

    slam_config_path = PathJoinSubstitution([pkg_smart_nav, 'config', 'slam_lifelong.yaml'])
    posegraph_path = PathJoinSubstitution([pkg_smart_nav, 'maps', LaunchConfiguration('map_name')])

    configured_params = RewrittenYaml(
        source_file=slam_config_path,
        root_key='',
        param_rewrites={'map_file_name': posegraph_path, 'mode': 'localization'},
        convert_types=True
    )

    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_slam_toolbox, 'launch', 'localization_launch.py'])),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'slam_params_file': configured_params 
        }.items()
    )

    return LaunchDescription([map_name_arg, use_sim_time_arg, slam_launch])