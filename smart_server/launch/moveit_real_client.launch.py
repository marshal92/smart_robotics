import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node

def generate_launch_description():
    moveit_config_dir = get_package_share_directory('smart_moveit_config')

    move_group = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(moveit_config_dir, 'launch', 'move_group.launch.py')),
        launch_arguments={'use_sim_time': 'false'}.items()
    )

    rviz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(moveit_config_dir, 'launch', 'moveit_rviz.launch.py')),
        launch_arguments={'use_sim_time': 'false'}.items()
    )

    bridge = Node(
        package='manipulator_core',
        executable='trajectory_bridge',
        output='screen',
        parameters=[{'use_sim_time': False}]
    )

    return LaunchDescription([
        move_group,
        rviz,
        bridge
    ])