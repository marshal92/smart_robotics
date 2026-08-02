from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition, UnlessCondition

def generate_launch_description():
    world_arg = DeclareLaunchArgument('world', default_value='213.sdf')
    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='false')
    
    use_sim_time = LaunchConfiguration('use_sim_time')

    rosbridge_node = Node(
        package='rosbridge_server',
        executable='rosbridge_websocket',
        name='rosbridge_websocket',
        output='screen',
        parameters=[{'max_message_size': 100000000}]
    )
    
    heartbeat_node = Node(
        package='smart_server',
        executable='heartbeat_pub',
        name='heartbeat_pub',
        output='screen'
    )
    
    sdf_visualizer_node = Node(
        package='smart_server',
        executable='sdf_visualizer',
        name='sdf_visualizer',
        output='screen',
        parameters=[{'world_file': LaunchConfiguration('world')}]
    )

    twin_orchestrator_node = Node(
        package='smart_server',
        executable='twin_orchestrator',
        name='twin_orchestrator',
        output='screen'
    )

    shadow_teleop_sim_node = Node(
        package='smart_server',
        executable='shadow_teleop_sim',
        name='shadow_teleop',
        output='screen',
        condition=IfCondition(use_sim_time),
        parameters=[{'use_sim_time': use_sim_time}]
    )

    shadow_teleop_real_node = Node(
        package='smart_server',
        executable='shadow_teleop_real',
        name='shadow_teleop',
        output='screen',
        condition=UnlessCondition(use_sim_time),
        parameters=[{'use_sim_time': use_sim_time}]
    )

    map_to_image_node = Node(
        package='smart_server',
        executable='map_to_image',
        name='map_to_image',
        output='screen'
    )

    web_server_node = Node(
        package='smart_server',
        executable='web_server',
        name='web_server',
        output='screen'
    )

    return LaunchDescription([
        world_arg,
        use_sim_time_arg,
        heartbeat_node,
        sdf_visualizer_node,
        twin_orchestrator_node,
        shadow_teleop_sim_node,
        shadow_teleop_real_node,
        rosbridge_node,
        map_to_image_node,
        web_server_node
    ])