from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition

def generate_launch_description():
    run_yolo_arg = DeclareLaunchArgument('run_yolo', default_value='false')
    run_ai_core_arg = DeclareLaunchArgument('run_ai_core', default_value='true')
    
    # New AI Core Nodes
    voice_listener = Node(
        condition=IfCondition(LaunchConfiguration('run_ai_core')),
        package='smart_ai',
        executable='voice_listener_node',
        name='voice_listener',
        output='screen',
        prefix='xterm -hold -e ' # Needed for spacebar input
    )

    dispatcher_node = Node(
        condition=IfCondition(LaunchConfiguration('run_ai_core')),
        package='smart_ai',
        executable='semantic_dispatcher_node',
        name='semantic_dispatcher',
        output='screen'
    )

    spatial_projector_node = Node(
        condition=IfCondition(LaunchConfiguration('run_ai_core')),
        package='smart_ai',
        executable='spatial_projector_node',
        name='spatial_projector',
        output='screen'
    )

    yolo_node = Node(
        condition=IfCondition(LaunchConfiguration('run_yolo')),
        package='smart_ai',
        executable='yolo_publisher',
        name='yolo_publisher',
        output='screen',
        parameters=[{'show_video': False}] 
    )

    return LaunchDescription([
        run_yolo_arg,
        run_ai_core_arg,
        voice_listener,
        dispatcher_node,
        spatial_projector_node,
        yolo_node
    ])