from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    
    require_heartbeat_arg = DeclareLaunchArgument('require_heartbeat', default_value='false')

    mission_manager_node = Node(
        package='smart_control',
        executable='mission_manager',
        name='mission_manager',
        output='screen',
        parameters=[{
            'is_simulation': use_sim_time,
            'spawn_x': LaunchConfiguration('spawn_x', default='0.0'),
            'spawn_y': LaunchConfiguration('spawn_y', default='0.0'),
            'spawn_yaw': LaunchConfiguration('spawn_yaw', default='0.0')
        }]
    )

    waypoint_manager_node = Node(
        package='smart_control',
        executable='waypoint_manager',
        name='waypoint_manager',
        output='screen'
    )

    safety_watchdog_node = Node(
        package='smart_control',
        executable='safety_watchdog',
        name='safety_watchdog',
        output='screen',
        parameters=[{'require_heartbeat': LaunchConfiguration('require_heartbeat')}]
    )

    nav_coordinator_node = Node(
        package='smart_control',
        executable='nav_coordinator',
        name='nav_coordinator',
        output='screen'
    )

    payload_manager_node = Node(
        package='smart_control',
        executable='payload_manager',
        name='payload_manager',
        output='screen'
    )

    telemetry_mux_node = Node(
        package='smart_plugins',
        executable='telemetry_mux',
        name='telemetry_mux',
        output='screen'
    )

    tactical_executor_node = Node(
        package='smart_control',
        executable='tactical_executor',
        name='tactical_executor',
        output='screen'
    )

    return LaunchDescription([
        require_heartbeat_arg,
        mission_manager_node,
        waypoint_manager_node,
        payload_manager_node,
        safety_watchdog_node,
        nav_coordinator_node,
        telemetry_mux_node,
        tactical_executor_node
    ])