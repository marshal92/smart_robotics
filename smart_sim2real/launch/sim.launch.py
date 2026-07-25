import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, AppendEnvironmentVariable, ExecuteProcess
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, Command
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.conditions import IfCondition, UnlessCondition
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg_sim = FindPackageShare('smart_sim2real')
    pkg_ros_gz_sim = FindPackageShare('ros_gz_sim')

    world_arg = DeclareLaunchArgument('world', default_value='213.sdf')
    gui_arg = DeclareLaunchArgument('gui', default_value='true')
    use_3d_lidar_arg = DeclareLaunchArgument('use_3d_lidar', default_value='false')
    god_mode_arg = DeclareLaunchArgument('god_mode', default_value='false')
    
    spawn_x_arg = DeclareLaunchArgument('spawn_x', default_value='0.0')
    spawn_y_arg = DeclareLaunchArgument('spawn_y', default_value='0.0')
    spawn_yaw_arg = DeclareLaunchArgument('spawn_yaw', default_value='0.0')

    use_3d_lidar = LaunchConfiguration('use_3d_lidar')
    god_mode = LaunchConfiguration('god_mode')

    world_path = PathJoinSubstitution([pkg_sim, 'worlds', LaunchConfiguration('world')])
    ekf_config_path = PathJoinSubstitution([pkg_sim, 'config', 'ekf_sim.yaml'])
    urdf_wrapper_path = PathJoinSubstitution([pkg_sim, 'urdf', 'sim_wrapper.urdf.xacro'])

    use_arm_arg = DeclareLaunchArgument('use_arm', default_value='true')
    use_arm = LaunchConfiguration('use_arm')

    set_model_path = AppendEnvironmentVariable('GZ_SIM_RESOURCE_PATH', PathJoinSubstitution([pkg_sim, 'models']))

    # Gazebo, find where to look for the manipulator_description package (we go up one level in the share folder)
    set_mesh_path = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', 
        PathJoinSubstitution([FindPackageShare('manipulator_description'), '..'])
    )

    gazebo_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py'])),
        launch_arguments={'gz_args': ['-r -s ', world_path]}.items()
    )

    gazebo_client = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py'])),
        condition=IfCondition(LaunchConfiguration('gui')),
        launch_arguments={'gz_args': ['-g']}.items()
    )

    rsp_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': ParameterValue(
                Command([
                    'xacro ', urdf_wrapper_path, 
                    ' sim:=true',
                    ' god_mode:=', god_mode,
                    ' use_3d_lidar:=', use_3d_lidar,
                    ' use_arm:=', use_arm
                ]), 
                value_type=str
            ),
            'use_sim_time': True
        }]
    )

    spawn_node = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=[
            '-name', 'ugv_tracked', 
            '-topic', 'robot_description', 
            '-x', LaunchConfiguration('spawn_x'), 
            '-y', LaunchConfiguration('spawn_y'), 
            '-z', '0.05',
            '-Y', LaunchConfiguration('spawn_yaw')
        ]
    )

    bridges_node = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        output='screen',
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist",
            "/odom/unfiltered@nav_msgs/msg/Odometry[gz.msgs.Odometry",
            "/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU"#,
            #"/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model"
        ]
    )

    gz_bridge_2d_node = Node(
        condition=UnlessCondition(use_3d_lidar),
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan"],
        output='screen'
    )

    gz_bridge_3d_node = Node(
        condition=IfCondition(use_3d_lidar),
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['/lidar3d/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked'],
        remappings=[('/lidar3d/points', '/points')],
        output='screen'
    )

    ekf_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[{'use_sim_time': True}, ekf_config_path],
        remappings=[("odometry/filtered", "/odom")]
    )

    # Smart mixer for simulation (Combines the arm from Gazebo and zeros for the wheels)
    jsp_node = Node(
        #condition=IfCondition(use_arm),
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher_sim',
        parameters=[{
            'use_sim_time': True,
            'source_list': ['/arm_joint_states']
        }]
    )

    # Load arm controller
    load_arm_controller = ExecuteProcess(
        condition=IfCondition(use_arm),
        cmd=['ros2', 'control', 'load_controller', '--set-state', 'active', 'arm_controller'],
        output='screen'
    )

    # Load joint state broadcaster
    load_joint_state_broadcaster = ExecuteProcess(
        condition=IfCondition(use_arm),
        cmd=['ros2', 'control', 'load_controller', '--set-state', 'active', 'joint_state_broadcaster'],
        output='screen'
    )

    return LaunchDescription([
        set_model_path, world_arg, gui_arg, use_3d_lidar_arg, god_mode_arg, set_mesh_path, use_arm_arg,
        spawn_x_arg, spawn_y_arg, spawn_yaw_arg, 
        gazebo_server, gazebo_client, rsp_node, spawn_node, bridges_node,
        gz_bridge_2d_node, 
        gz_bridge_3d_node, 
        #pc_to_laserscan_node, 
        ekf_node,
        load_arm_controller,
        load_joint_state_broadcaster,
        jsp_node
    ])