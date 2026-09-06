import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node

def generate_launch_description():
    map_path_arg = DeclareLaunchArgument(
        'map_path',
        default_value='explored_map.npy',
        description='Path to the working radiation map (will be created in maps/ if not absolute)'
    )
    
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation (Gazebo) clock if true'
    )
    
    use_virtual_geiger_arg = DeclareLaunchArgument(
        'use_virtual_geiger',
        default_value='true',
        description='Start the simulated geiger counter (set to false on real robot)'
    )

    use_sim_time = LaunchConfiguration('use_sim_time')

    radiation_field_server_node = Node(
        package='smart_radiation',
        executable='radiation_field_server',
        name='radiation_field_server',
        output='screen',
        parameters=[{
            'map_path': LaunchConfiguration('map_path'),
            'use_sim_time': use_sim_time
        }]
    )

    radiation_mapper_node = Node(
        package='smart_radiation',
        executable='radiation_mapper',
        name='radiation_mapper',
        output='screen',
        parameters=[{
            'map_path': LaunchConfiguration('map_path'),
            'use_sim_time': use_sim_time
        }]
    )

    alara_reflex_node = Node(
        package='smart_plugins',
        executable='alara_speed_reflex_node',
        name='alara_speed_reflex_node',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}]
    )
    
    virtual_geiger_node = Node(
        package='smart_radiation',
        executable='virtual_geiger',
        name='virtual_geiger',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_virtual_geiger')),
        parameters=[{'use_sim_time': use_sim_time}]
    )

    return LaunchDescription([
        map_path_arg,
        use_sim_time_arg,
        use_virtual_geiger_arg,
        radiation_field_server_node,
        radiation_mapper_node,
        virtual_geiger_node,
        alara_reflex_node
    ])
