from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, Command
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    use_sim_time = 'false'
    pkg_smart_master = FindPackageShare('smart_master')

    use_arm_arg = DeclareLaunchArgument('use_arm', default_value='true')
    use_arm = LaunchConfiguration('use_arm')

    # Global URDF (Master Assembly)
    urdf_path = PathJoinSubstitution([pkg_smart_master, 'urdf', 'full_system.urdf.xacro'])
    
    rsp_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': ParameterValue(
                Command(['xacro ', urdf_path, ' sim:=false', ' use_arm:=', use_arm]),
                value_type=str
            ),
            'use_sim_time': False
        }]
    )

    # Smart mixer for combining wheels and arm
    jsp_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        parameters=[{
            'use_sim_time': False,
            'source_list': ['/arm_joint_states']
        }]
    )

    # Robot
    hardware_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare('ugv_tracked_bringup'), 'launch', 'hardware.launch.py']))
    )

    # Control (Nav2, Behaviour Trees, Controllers)
    control_core_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare('smart_control'), 'launch', 'control_core.launch.py'])),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'require_heartbeat': 'false' # Поставь 'true', если Пульс с сервера уже стабильно долетает
        }.items()
    )

    # Subsystems (Radiation and Reflexes)
    radiation_server_node = Node(
        package='smart_radiation',
        executable='radiation_field_server',
        name='radiation_field_server',
        output='screen',
        parameters=[{'use_sim_time': False}]
    )

    alara_reflex_node = Node(
        package='smart_plugins',
        executable='alara_speed_reflex_node',
        name='alara_speed_reflex_node',
        output='screen',
        parameters=[{'use_sim_time': False}]
    )

    return LaunchDescription([
        use_arm_arg,
        hardware_launch,
        control_core_launch,
        radiation_server_node,
        alara_reflex_node,
        rsp_node,
        jsp_node
    ])