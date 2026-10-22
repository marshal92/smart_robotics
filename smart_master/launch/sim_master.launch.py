import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.conditions import IfCondition

def generate_launch_description():
    pkg_sim = FindPackageShare('smart_sim2real')

    use_3d_lidar_arg = DeclareLaunchArgument('use_3d_lidar', default_value='false')
    stabilize_lidar_arg = DeclareLaunchArgument('stabilize_lidar', default_value='true')
    god_mode_arg = DeclareLaunchArgument('god_mode', default_value='false')
    gui_arg = DeclareLaunchArgument('gui', default_value='false')
    world_arg = DeclareLaunchArgument('world', default_value='213.sdf')
    spawn_x_arg = DeclareLaunchArgument('spawn_x', default_value='0.0')
    spawn_y_arg = DeclareLaunchArgument('spawn_y', default_value='0.0')
    spawn_yaw_arg = DeclareLaunchArgument('spawn_yaw', default_value='0.0')
    use_arm_arg = DeclareLaunchArgument('use_arm', default_value='false')

    use_sim_time = 'true'

    simulation_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_sim, 'launch', 'sim.launch.py'])),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'gui': LaunchConfiguration('gui'),
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


    radiation_bringup_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare('smart_radiation'), 'launch', 'radiation_bringup.launch.py'])),
        launch_arguments={
            'map_path': 'explored_map.npy'
        }.items()
    )

    stabilized_frame_node = Node(
        package='smart_plugins',
        executable='stabilized_frame_publisher_node',
        name='stabilized_frame_publisher',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_3d_lidar')),
        parameters=[{
            'use_sim_time': True,
            'stabilize': ParameterValue(LaunchConfiguration('stabilize_lidar'), value_type=bool),
            'min_height': 0.30,
            'max_height': 0.80,
            'low_min_height': 0.10,
            'low_max_height': 0.30,
            'min_step_height': 0.09
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
        use_3d_lidar_arg, stabilize_lidar_arg, god_mode_arg, gui_arg, world_arg, use_arm_arg,
        spawn_x_arg, spawn_y_arg, spawn_yaw_arg,
        simulation_launch,
        control_core_launch,
        radiation_bringup_launch,
        stabilized_frame_node,
        server_launch
    ])