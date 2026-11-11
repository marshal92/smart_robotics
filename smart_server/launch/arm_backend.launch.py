import os
import yaml
from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from ament_index_python.packages import get_package_share_directory
from moveit_configs_utils import MoveItConfigsBuilder


def load_yaml(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)
    try:
        with open(absolute_file_path, "r") as file:
            return yaml.safe_load(file)
    except OSError:
        return None


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='true')
    use_sim_time = ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)

    use_arm_arg = DeclareLaunchArgument('use_arm', default_value='true')
    use_arm = LaunchConfiguration('use_arm')

    use_rviz_arg = DeclareLaunchArgument('use_rviz', default_value='false')
    use_rviz = LaunchConfiguration('use_rviz')

    # Load MoveIt configuration from smart_moveit_config
    moveit_config = (
        MoveItConfigsBuilder("smart_robot", package_name="smart_moveit_config")
        .robot_description(file_path="config/smart_robot.urdf.xacro")
        .robot_description_semantic(file_path="config/smart_robot.srdf")
        .trajectory_execution(file_path="config/moveit_controllers.yaml")
        .to_moveit_configs()
    )

    # 1. MoveIt move_group (embedded directly without launching a separate file or extra RViz)
    move_group_configuration = {
        "publish_robot_description_semantic": True,
        "allow_trajectory_execution": True,
        "capabilities": ParameterValue(
            moveit_config.move_group_capabilities.get("capabilities", ""), value_type=str
        ),
        "disable_capabilities": ParameterValue(
            moveit_config.move_group_capabilities.get("disable_capabilities", ""), value_type=str
        ),
        "publish_planning_scene": ParameterValue(use_rviz, value_type=bool),
        "publish_geometry_updates": ParameterValue(use_rviz, value_type=bool),
        "publish_state_updates": ParameterValue(use_rviz, value_type=bool),
        "publish_transforms_updates": ParameterValue(use_rviz, value_type=bool),
        "monitor_dynamics": False,
        "use_sim_time": use_sim_time,
    }

    move_group_node = Node(
        condition=IfCondition(use_arm),
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            move_group_configuration,
        ],
    )

    # 2. Optional RViz2 (disabled by default: use_rviz:=false)
    rviz_config_file = os.path.join(
        get_package_share_directory("smart_moveit_config"), "config", "moveit.rviz"
    )
    rviz_node = Node(
        condition=IfCondition(use_rviz),
        package="rviz2",
        executable="rviz2",
        name="rviz2_moveit",
        output="log",
        arguments=["-d", rviz_config_file],
        parameters=[
            moveit_config.planning_pipelines,
            moveit_config.robot_description_kinematics,
            moveit_config.joint_limits,
            {"use_sim_time": use_sim_time},
        ],
    )

    # 3. Load Servo Configuration
    servo_yaml = load_yaml("smart_moveit_config", "config/servo_config.yaml")
    servo_params = {"moveit_servo": servo_yaml}

    tactical_server_node = Node(
        condition=IfCondition(use_arm),
        package="manipulator_control",
        executable="tactical_server",
        name="tactical_server",
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            {'use_sim_time': use_sim_time},
        ],
        output="screen",
    )

    control_hub_node = Node(
        condition=IfCondition(use_arm),
        package="manipulator_control",
        executable="control_hub",
        name="control_hub",
        output="screen",
        parameters=[{'use_sim_time': use_sim_time}],
    )

    teleop_manager_node = Node(
        condition=IfCondition(use_arm),
        package="manipulator_control",
        executable="teleop_manager",
        name="teleop_manager",
        output="screen",
        parameters=[{'use_sim_time': use_sim_time}],
    )

    servo_node = Node(
        condition=IfCondition(use_arm),
        package="moveit_servo",
        executable="servo_node",
        parameters=[
            servo_params,
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            {'use_sim_time': use_sim_time},
        ],
        output="screen",
    )

    return LaunchDescription([
        use_sim_time_arg,
        use_arm_arg,
        use_rviz_arg,
        move_group_node,
        rviz_node,
        tactical_server_node,
        control_hub_node,
        teleop_manager_node,
        servo_node,
    ])
