import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import SetParameter

def generate_launch_description():
    moveit_config_dir = get_package_share_directory('smart_moveit_config')

    # Load MoveIt Brain
    # It will automatically connect to global topics /joint_states and /tf
    move_group = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(moveit_config_dir, 'launch', 'move_group.launch.py')),
        launch_arguments={'use_sim_time': 'true'}.items()
    )

    # Load RViz interface
    rviz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(moveit_config_dir, 'launch', 'moveit_rviz.launch.py')),
        launch_arguments={'use_sim_time': 'true'}.items()
    )

    return LaunchDescription([
        # Gazebo time synchronization
        SetParameter(name='use_sim_time', value=True),
        
        move_group,
        rviz
    ])