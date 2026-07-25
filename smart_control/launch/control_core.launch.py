from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    
    require_heartbeat_arg = DeclareLaunchArgument('require_heartbeat', default_value='true')

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

#    mission_control_node = Node(
#        package='smart_control',
#        executable='mission_control',
#        name='mission_control',
#        output='screen',
#        parameters=[{
#            'use_sim_time': use_sim_time,
#            'require_heartbeat': LaunchConfiguration('require_heartbeat')
#        }]
#    )

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
    return LaunchDescription([
        require_heartbeat_arg,
        mission_manager_node,
#       mission_control_node,
        waypoint_manager_node,
        payload_manager_node,
        safety_watchdog_node,
        nav_coordinator_node
    ])