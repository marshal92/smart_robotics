import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node
from launch.conditions import IfCondition

def generate_launch_description():
    pkg_sim = FindPackageShare('smart_sim2real')

    use_3d_lidar_arg = DeclareLaunchArgument('use_3d_lidar', default_value='false')
    god_mode_arg = DeclareLaunchArgument('god_mode', default_value='false')
    world_arg = DeclareLaunchArgument('world', default_value='213.sdf')
    spawn_x_arg = DeclareLaunchArgument('spawn_x', default_value='0.0')
    spawn_y_arg = DeclareLaunchArgument('spawn_y', default_value='0.0')
    spawn_yaw_arg = DeclareLaunchArgument('spawn_yaw', default_value='0.0')
    use_arm_arg = DeclareLaunchArgument('use_arm', default_value='true')

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
            'spawn_yaw': LaunchConfiguration('spawn_yaw'),
            'use_arm': LaunchConfiguration('use_arm')
        }.items()
    )

    control_core_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare('smart_control'), 'launch', 'control_core.launch.py'])),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'require_heartbeat': 'false',
            'spawn_x': LaunchConfiguration('spawn_x'),
            'spawn_y': LaunchConfiguration('spawn_y'),
            'spawn_yaw': LaunchConfiguration('spawn_yaw')
        }.items()
    )

    radiation_server_node = Node(
        package='smart_radiation',
        executable='radiation_field_server',
        name='radiation_field_server',
        output='screen'
    )

    alara_reflex_node = Node(
        package='smart_plugins',
        executable='alara_speed_reflex_node',
        name='alara_speed_reflex_node',
        output='screen'
    )

    stabilized_frame_node = Node(
        package='smart_plugins',
        executable='stabilized_frame_publisher_node',
        name='stabilized_frame_publisher',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_3d_lidar')),
        parameters=[{'use_sim_time': True}]
    )
    
    pc_to_laserscan_node = Node(
        condition=IfCondition(LaunchConfiguration('use_3d_lidar')),
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='pc_to_laserscan',
        output='screen',
        remappings=[('cloud_in', '/points'), ('scan', '/scan')],
        parameters=[{
            'target_frame': 'base_stabilized',
            'min_height': 0.22,
            'max_height': 1.0,
            'angle_min': -3.14159, 
            'angle_max': 3.14159,
            'range_min': 0.15,
            'range_max': 10.0,
            'use_inf': True,
            'use_sim_time': True
        }]
    )

    server_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare('smart_server'), 'launch', 'server.launch.py'])),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'use_sim_time': use_sim_time
        }.items()
    )
    
    return LaunchDescription([
        use_3d_lidar_arg, god_mode_arg, world_arg, use_arm_arg,
        spawn_x_arg, spawn_y_arg, spawn_yaw_arg,
        simulation_launch,
        control_core_launch,
        radiation_server_node,
        alara_reflex_node,
        stabilized_frame_node,
        pc_to_laserscan_node,
        server_launch
    ])