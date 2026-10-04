import os
import yaml
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
from moveit_configs_utils import MoveItConfigsBuilder

from launch.conditions import IfCondition

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
    use_sim_time = LaunchConfiguration('use_sim_time')
    
    use_arm_arg = DeclareLaunchArgument('use_arm', default_value='true')
    use_arm = LaunchConfiguration('use_arm')

    # Load MoveIt configuration from smart_moveit_config!
    moveit_config = MoveItConfigsBuilder("smart_robot", package_name="smart_moveit_config") \
        .robot_description(file_path="config/smart_robot.urdf.xacro") \
        .robot_description_semantic(file_path="config/smart_robot.srdf") \
        .trajectory_execution(file_path="config/moveit_controllers.yaml") \
        .to_moveit_configs()

    # Load Servo Configuration
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
            {'use_sim_time': use_sim_time}
        ],
        output="screen",
    )

    return LaunchDescription([
        use_sim_time_arg,
        use_arm_arg,
        tactical_server_node,
        control_hub_node,
        teleop_manager_node,
        servo_node,
    ])
