import os
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from moveit_configs_utils import MoveItConfigsBuilder


def load_yaml(package_name, file_path):
    """Load YAML configuration from an ament package share directory."""
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)
    try:
        with open(absolute_file_path, "r") as file:
            return yaml.safe_load(file) or {}
    except OSError:
        return {}


def generate_launch_description():
    """Launch standalone MoveIt Servo and teleop_manager (no move_group required)."""
    use_sim_time_arg = DeclareLaunchArgument("use_sim_time", default_value="true")
    use_sim_time = ParameterValue(LaunchConfiguration("use_sim_time"), value_type=bool)

    moveit_config = (
        MoveItConfigsBuilder("smart_robot", package_name="smart_moveit_config")
        .robot_description(file_path="config/smart_robot.urdf.xacro")
        .robot_description_semantic(file_path="config/smart_robot.srdf")
        .robot_description_kinematics(file_path="config/kinematics.yaml")
        .to_moveit_configs()
    )

    servo_yaml = load_yaml("smart_moveit_config", "config/servo_config.yaml")
    # Ensure servo_node owns its planning scene monitor so it runs independently of move_group
    servo_yaml["is_primary_planning_scene_monitor"] = True
    servo_params = {"moveit_servo": servo_yaml}

    teleop_manager_node = Node(
        package="manipulator_control",
        executable="teleop_manager",
        name="teleop_manager",
        output="screen",
        parameters=[{"use_sim_time": use_sim_time}],
    )

    servo_node = Node(
        package="moveit_servo",
        executable="servo_node",
        parameters=[
            servo_params,
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.joint_limits,
            {"use_sim_time": use_sim_time},
        ],
        output="screen",
    )

    return LaunchDescription([
        use_sim_time_arg,
        teleop_manager_node,
        servo_node,
    ])
