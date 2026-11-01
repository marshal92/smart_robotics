from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, Command
from launch.conditions import IfCondition, UnlessCondition
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    world_arg = DeclareLaunchArgument('world', default_value='213.sdf')
    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='false')
    use_arm_arg = DeclareLaunchArgument('use_arm', default_value='false')
    
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_arm = LaunchConfiguration('use_arm')

    pkg_smart_master = FindPackageShare('smart_master')
    urdf_path = PathJoinSubstitution([pkg_smart_master, 'urdf', 'full_system.urdf.xacro'])

    # Локальные RSP и JSP на сервере (только для реального робота, когда use_sim_time=false),
    # чтобы Web UI 2.0 и RViz получали URDF (/robot_state_publisher/get_parameters и /joint_states)
    # локально без забивания радиоканала Zenoh.
    rsp_real_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        condition=UnlessCondition(use_sim_time),
        parameters=[{
            'robot_description': ParameterValue(
                Command(['xacro ', urdf_path, ' sim:=false', ' use_arm:=', use_arm]),
                value_type=str
            ),
            'use_sim_time': False
        }],
        remappings=[('/tf', '/tf_server_local')]
    )

    jsp_real_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        condition=UnlessCondition(use_sim_time),
        parameters=[{
            'use_sim_time': False,
            'source_list': ['/arm_joint_states']
        }]
    )

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
        parameters=[{'use_sim_time': False, 'worker_use_sim_time': use_sim_time}]
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
        use_arm_arg,
        rsp_real_node,
        jsp_real_node,
        heartbeat_node,
        sdf_visualizer_node,
        twin_orchestrator_node,
        shadow_teleop_sim_node,
        shadow_teleop_real_node,
        rosbridge_node,
        map_to_image_node,
        web_server_node
    ])