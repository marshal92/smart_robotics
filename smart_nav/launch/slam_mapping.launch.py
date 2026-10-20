import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from nav2_common.launch import RewrittenYaml


def _launch_slam(context, *args, **kwargs):
    pkg_smart_nav = FindPackageShare('smart_nav')
    pkg_slam_toolbox = FindPackageShare('slam_toolbox')

    map_name = LaunchConfiguration('map_name').perform(context).strip()
    slam_config_path = PathJoinSubstitution([pkg_smart_nav, 'config', 'slam_mapping.yaml'])

    if map_name and map_name.lower() != 'none':
        posegraph_path = PathJoinSubstitution([pkg_smart_nav, 'maps', map_name]).perform(context)
        rewritten = RewrittenYaml(
            source_file=slam_config_path,
            root_key='',
            param_rewrites={'map_file_name': posegraph_path, 'mode': 'mapping'},
            convert_types=True
        )
        params_file = rewritten.perform(context)
    else:
        params_file = slam_config_path.perform(context)

    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_slam_toolbox, 'launch', 'online_async_launch.py'])),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'slam_params_file': params_file
        }.items()
    )
    return [slam_launch]


def generate_launch_description():
    map_name_arg = DeclareLaunchArgument('map_name', default_value='none')
    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='true')

    return LaunchDescription([
        map_name_arg,
        use_sim_time_arg,
        OpaqueFunction(function=_launch_slam)
    ])