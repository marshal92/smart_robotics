import os
import xacro
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, GroupAction
from launch_ros.actions import PushRosNamespace, SetRemap, Node, SetParameter
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    moveit_config_pkg = get_package_share_directory('manipulator_moveit_config')
    
    # Load blank URDF for the arm
    arm_desc_path = os.path.join(
        get_package_share_directory('manipulator_description'), 
        'urdf', 
        'robot_arm.urdf.xacro'
    )
    arm_doc = xacro.process_file(arm_desc_path)
    robot_description = {'robot_description': arm_doc.toxml()}

    # Load SRDF configuration for MoveIt
    srdf_path = os.path.join(moveit_config_pkg, 'config', 'manipulator_full.srdf')
    with open(srdf_path, 'r') as f:
        robot_description_semantic = {'robot_description_semantic': f.read()}

    # Isolated MoveIt Brain
    arm_moveit_group = GroupAction(
        actions=[
            PushRosNamespace('arm'),
            SetParameter(name='use_sim_time', value=True),
            
            # Read real joint states from simulation
            SetRemap(src='/arm/joint_states', dst='/joint_states'),
            
            # Isolated RSP for MoveIt
            Node(
                package='robot_state_publisher',
                executable='robot_state_publisher',
                name='isolated_arm_rsp',
                parameters=[robot_description],
                remappings=[
                    ('/tf', '/tf_isolated'),
                    ('/tf_static', '/tf_static_isolated')
                ]
            ),
            
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(os.path.join(moveit_config_pkg, 'launch', 'move_group.launch.py'))
            )
        ]
    )

    # Global RViz with hard-coded parameters
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2_global',
        output='screen',
        parameters=[
            robot_description,
            robot_description_semantic,
            {'use_sim_time': True}
        ],
        arguments=['-d', ''] # Launch clean config to avoid old bugs
    )

    return LaunchDescription([arm_moveit_group, rviz_node])