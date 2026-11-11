import os
from pathlib import Path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory


def _default_maps_dir():
    env_dir = os.environ.get('SMART_RADIATION_MAPS_DIR', '').strip()
    if env_dir:
        return os.path.expanduser(env_dir)
    pkg_maps = Path(__file__).resolve().parent.parent / 'maps'
    if pkg_maps.exists():
        return str(pkg_maps)
    ws_maps = Path.home() / 'ros2_ws' / 'src' / 'smart_robotics' / 'smart_radiation' / 'maps'
    if ws_maps.exists():
        return str(ws_maps)
    try:
        return os.path.join(get_package_share_directory('smart_radiation'), 'maps')
    except Exception:
        return str(ws_maps)


def _default_params_file():
    ws_cfg = Path.home() / 'ros2_ws' / 'src' / 'smart_robotics' / 'smart_radiation' / 'config' / 'radiation_params.yaml'
    if ws_cfg.exists():
        return str(ws_cfg)
    try:
        return os.path.join(get_package_share_directory('smart_radiation'), 'config', 'radiation_params.yaml')
    except Exception:
        return str(ws_cfg)


def generate_launch_description():
    maps_dir_arg = DeclareLaunchArgument(
        'maps_dir',
        default_value=_default_maps_dir(),
        description='Directory containing working and reference radiation maps'
    )

    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=_default_params_file(),
        description='YAML file with radiation thresholds (d_noise, d_crit, k)'
    )

    map_path_arg = DeclareLaunchArgument(
        'map_path',
        default_value='explored_map.npy',
        description='Path to the working radiation map (resolved in maps_dir if relative)'
    )

    sensor_map_path_arg = DeclareLaunchArgument(
        'sensor_map_path',
        default_value='radiation_map_complex.npy',
        description='Path to the ground-truth radiation field for virtual_geiger only'
    )

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation (Gazebo) clock if true'
    )

    use_virtual_geiger_arg = DeclareLaunchArgument(
        'use_virtual_geiger',
        default_value='true',
        description='Start the simulated geiger counter node (stays idle until activated by command)'
    )

    use_alara_reflex_arg = DeclareLaunchArgument(
        'use_alara_reflex',
        default_value='false',
        description='Enable or disable the ALARA speed reflex plugin'
    )

    initial_active_arg = DeclareLaunchArgument(
        'initial_active',
        default_value='false',
        description='Automatically activate radiation field upon startup'
    )

    use_sim_time = ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)
    use_virtual_geiger = ParameterValue(LaunchConfiguration('use_virtual_geiger'), value_type=bool)
    initial_active = ParameterValue(LaunchConfiguration('initial_active'), value_type=bool)
    params_file = LaunchConfiguration('params_file')

    radiation_field_server_node = Node(
        package='smart_radiation',
        executable='radiation_field_server',
        name='radiation_field_server',
        output='screen',
        parameters=[
            params_file,
            {
                'maps_dir': LaunchConfiguration('maps_dir'),
                'map_path': LaunchConfiguration('map_path'),
                'use_sim_time': False
            }
        ]
    )

    radiation_mapper_node = Node(
        package='smart_radiation_plugins',
        executable='radiation_mapper_node',
        name='radiation_mapper',
        output='screen',
        parameters=[
            params_file,
            {
                'maps_dir': LaunchConfiguration('maps_dir'),
                'map_path': LaunchConfiguration('map_path'),
                'use_sim_time': False,
                'worker_use_sim_time': use_sim_time
            }
        ]
    )

    alara_reflex_node = Node(
        package='smart_radiation_plugins',
        executable='alara_speed_reflex_node',
        name='alara_speed_reflex_node',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_alara_reflex')),
        parameters=[
            params_file,
            {'use_sim_time': use_sim_time}
        ]
    )

    virtual_geiger_node = Node(
        package='smart_radiation_plugins',
        executable='virtual_geiger_node',
        name='virtual_geiger',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_virtual_geiger')),
        parameters=[{
            'maps_dir': LaunchConfiguration('maps_dir'),
            'map_path': LaunchConfiguration('sensor_map_path'),
            'use_sim_time': False,
            'worker_use_sim_time': use_sim_time
        }]
    )

    radiation_manager_node = Node(
        package='smart_radiation',
        executable='radiation_manager',
        name='radiation_manager',
        output='screen',
        parameters=[{
            'maps_dir': LaunchConfiguration('maps_dir'),
            'map_path': LaunchConfiguration('map_path'),
            'use_virtual_geiger': use_virtual_geiger,
            'initial_active': initial_active,
            'use_sim_time': False
        }]
    )

    return LaunchDescription([
        maps_dir_arg,
        params_file_arg,
        map_path_arg,
        sensor_map_path_arg,
        use_sim_time_arg,
        use_virtual_geiger_arg,
        use_alara_reflex_arg,
        initial_active_arg,
        radiation_field_server_node,
        radiation_mapper_node,
        virtual_geiger_node,
        alara_reflex_node,
        radiation_manager_node
    ])
