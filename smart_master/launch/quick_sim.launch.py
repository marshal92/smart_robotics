import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.conditions import IfCondition
from launch.substitutions import EqualsSubstitution
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    pkg_sim = FindPackageShare('smart_sim2real')
    pkg_nav = FindPackageShare('smart_nav')

    slam_mode_arg = DeclareLaunchArgument(
        'slam_mode', 
        default_value='lifelong', 
        description='SLAM mode: mapping or lifelong'
    )
    
    map_name_arg = DeclareLaunchArgument(
        'map_name', 
        default_value='new_213_map', 
        description='Map name for lifelong mode'
    )

    use_3d_lidar_arg = DeclareLaunchArgument('use_3d_lidar', default_value='false')
    god_mode_arg = DeclareLaunchArgument('god_mode', default_value='false')

    world_arg = DeclareLaunchArgument('world', default_value='213.sdf')
    spawn_x_arg = DeclareLaunchArgument('spawn_x', default_value='0.0')
    spawn_y_arg = DeclareLaunchArgument('spawn_y', default_value='0.0')
    spawn_yaw_arg = DeclareLaunchArgument('spawn_yaw', default_value='0.0')

    use_sim_time = 'true'

    simulation_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_sim, 'launch', 'sim.launch.py'])),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'use_3d_lidar': LaunchConfiguration('use_3d_lidar'),
            'god_mode': LaunchConfiguration('god_mode'),
            'world': LaunchConfiguration('world'),
            'spawn_x': LaunchConfiguration('spawn_x'),
            'spawn_y': LaunchConfiguration('spawn_y'),
            'spawn_yaw': LaunchConfiguration('spawn_yaw')
        }.items()
    )
    
    mapping_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_nav, 'launch', 'bringup_mapping.launch.py'])),
        condition=IfCondition(EqualsSubstitution(LaunchConfiguration('slam_mode'), 'mapping')),
        launch_arguments={'use_sim_time': use_sim_time}.items()
    )

    lifelong_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_nav, 'launch', 'bringup_lifelong.launch.py'])),
        condition=IfCondition(EqualsSubstitution(LaunchConfiguration('slam_mode'), 'lifelong')),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'map_name': LaunchConfiguration('map_name')
        }.items()
    )

    return LaunchDescription([
        slam_mode_arg,
        map_name_arg,
        use_3d_lidar_arg,
        god_mode_arg,
        world_arg,          
        spawn_x_arg,        
        spawn_y_arg,        
        spawn_yaw_arg,      
        simulation_launch,
        mapping_launch,
        lifelong_launch
    ])