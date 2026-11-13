from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    """Launch MoveIt move_group, tactical_server, and control_hub (for AUTO & GOTO_XYZ)."""
    use_sim_time_arg = DeclareLaunchArgument("use_sim_time", default_value="true")
    use_sim_time = ParameterValue(LaunchConfiguration("use_sim_time"), value_type=bool)

    moveit_config = (
        MoveItConfigsBuilder("smart_robot", package_name="smart_moveit_config")
        .robot_description(file_path="config/smart_robot.urdf.xacro")
        .robot_description_semantic(file_path="config/smart_robot.srdf")
        .robot_description_kinematics(file_path="config/kinematics.yaml")
        .trajectory_execution(file_path="config/moveit_controllers.yaml")
        .to_moveit_configs()
    )

    move_group_configuration = {
        "publish_robot_description_semantic": True,
        "allow_trajectory_execution": True,
        "capabilities": ParameterValue(
            moveit_config.move_group_capabilities.get("capabilities", ""), value_type=str
        ),
        "disable_capabilities": ParameterValue(
            moveit_config.move_group_capabilities.get("disable_capabilities", ""), value_type=str
        ),
        "publish_planning_scene": False,
        "publish_geometry_updates": False,
        "publish_state_updates": False,
        "publish_transforms_updates": False,
        "monitor_dynamics": False,
        "use_sim_time": use_sim_time,
    }

    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            move_group_configuration,
        ],
    )

    tactical_server_node = Node(
        package="manipulator_control",
        executable="tactical_server",
        name="tactical_server",
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.joint_limits,
            {"use_sim_time": use_sim_time},
        ],
        output="screen",
    )

    control_hub_node = Node(
        package="manipulator_control",
        executable="control_hub",
        name="control_hub",
        output="screen",
        parameters=[{"use_sim_time": use_sim_time}],
    )

    return LaunchDescription([
        use_sim_time_arg,
        move_group_node,
        tactical_server_node,
        control_hub_node,
    ])
