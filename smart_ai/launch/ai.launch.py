from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition

def generate_launch_description():
    run_yolo_arg = DeclareLaunchArgument('run_yolo', default_value='false')
    run_ears_arg = DeclareLaunchArgument('run_ears', default_value='false')
    
    ears_node = Node(
        condition=IfCondition(LaunchConfiguration('run_ears')),
        package='smart_ai',
        executable='smart_ears',
        name='smart_ears',
        output='screen',
        prefix='xterm -hold -e ' 
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
        run_ears_arg,
        ears_node,
        yolo_node
    ])