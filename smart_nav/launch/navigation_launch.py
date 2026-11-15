# Adapted from nav2_bringup/launch/navigation_launch.py (Apache-2.0, Intel Corporation)
# Customized for smart_nav: supports optional route_server/docking_server toggles
# and optional in-launch component_container_isolated creation for composed Nav2.

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, OpaqueFunction, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LoadComposableNodes, Node, SetParameter
from launch_ros.descriptions import ComposableNode, ParameterFile
from nav2_common.launch import RewrittenYaml


_NAV2_SERVERS = (
    {
        'name': 'controller_server',
        'package': 'nav2_controller',
        'executable': 'controller_server',
        'plugin': 'nav2_controller::ControllerServer',
        'cmd_vel_remap': True,
        'flag': None,
    },
    {
        'name': 'smoother_server',
        'package': 'nav2_smoother',
        'executable': 'smoother_server',
        'plugin': 'nav2_smoother::SmootherServer',
        'cmd_vel_remap': False,
        'flag': None,
    },
    {
        'name': 'planner_server',
        'package': 'nav2_planner',
        'executable': 'planner_server',
        'plugin': 'nav2_planner::PlannerServer',
        'cmd_vel_remap': False,
        'flag': None,
    },
    {
        'name': 'route_server',
        'package': 'nav2_route',
        'executable': 'route_server',
        'plugin': 'nav2_route::RouteServer',
        'cmd_vel_remap': False,
        'flag': 'use_route',
    },
    {
        'name': 'behavior_server',
        'package': 'nav2_behaviors',
        'executable': 'behavior_server',
        'plugin': 'behavior_server::BehaviorServer',
        'cmd_vel_remap': True,
        'flag': None,
    },
    {
        'name': 'velocity_smoother',
        'package': 'nav2_velocity_smoother',
        'executable': 'velocity_smoother',
        'plugin': 'nav2_velocity_smoother::VelocitySmoother',
        'cmd_vel_remap': True,
        'flag': None,
    },
    {
        'name': 'collision_monitor',
        'package': 'nav2_collision_monitor',
        'executable': 'collision_monitor',
        'plugin': 'nav2_collision_monitor::CollisionMonitor',
        'cmd_vel_remap': False,
        'flag': None,
    },
    {
        'name': 'bt_navigator',
        'package': 'nav2_bt_navigator',
        'executable': 'bt_navigator',
        'plugin': 'nav2_bt_navigator::BtNavigator',
        'cmd_vel_remap': False,
        'flag': None,
    },
    {
        'name': 'waypoint_follower',
        'package': 'nav2_waypoint_follower',
        'executable': 'waypoint_follower',
        'plugin': 'nav2_waypoint_follower::WaypointFollower',
        'cmd_vel_remap': False,
        'flag': None,
    },
    {
        'name': 'docking_server',
        'package': 'opennav_docking',
        'executable': 'opennav_docking',
        'plugin': 'opennav_docking::DockingServer',
        'cmd_vel_remap': False,
        'flag': 'use_docking',
    },
)


def _parse_bool(context, arg_name: str) -> bool:
    raw = LaunchConfiguration(arg_name).perform(context).strip().lower()
    if raw in ('true', '1', 'yes', 'on'):
        return True
    if raw in ('false', '0', 'no', 'off'):
        return False
    raise ValueError(f"Invalid boolean value '{raw}' for launch argument '{arg_name}'")


def _container_full_name(namespace: str, container_name: str) -> str:
    ns = namespace.strip('/')
    cname = container_name.lstrip('/')
    return f'/{ns}/{cname}' if ns else f'/{cname}'


def _launch_navigation(context, *args, **kwargs):
    namespace = LaunchConfiguration('namespace').perform(context).strip()
    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart = LaunchConfiguration('autostart')
    params_file = LaunchConfiguration('params_file')
    use_composition = _parse_bool(context, 'use_composition')
    create_container = _parse_bool(context, 'create_container')
    container_name = LaunchConfiguration('container_name').perform(context).strip()
    use_respawn = _parse_bool(context, 'use_respawn')
    log_level = LaunchConfiguration('log_level')
    use_docking = _parse_bool(context, 'use_docking')
    use_route = _parse_bool(context, 'use_route')

    flags = {
        'use_docking': use_docking,
        'use_route': use_route,
    }
    active_servers = [
        srv for srv in _NAV2_SERVERS
        if srv['flag'] is None or flags[srv['flag']]
    ]
    lifecycle_nodes = [srv['name'] for srv in active_servers]

    # Map fully qualified names to relative ones so the node's namespace can be prepended.
    remappings = [('/tf', 'tf'), ('/tf_static', 'tf_static')]

    configured_params = ParameterFile(
        RewrittenYaml(
            source_file=params_file,
            root_key=namespace,
            param_rewrites={'autostart': autostart},
            convert_types=True,
        ),
        allow_substs=True,
    )

    actions = [SetParameter('use_sim_time', use_sim_time)]

    if use_composition:
        if create_container:
            actions.append(
                Node(
                    name=container_name,
                    namespace=namespace,
                    package='rclcpp_components',
                    executable='component_container_isolated',
                    parameters=[configured_params, {'autostart': autostart}],
                    arguments=['--ros-args', '--log-level', log_level],
                    remappings=remappings,
                    output='screen',
                )
            )

        # Load lifecycle_manager first so its rcl preshutdown runs before managed servers
        # tear down, avoiding a false 4s bond timeout and SIGTERM escalation on SIGINT.
        composable_nodes = [
            ComposableNode(
                package='nav2_lifecycle_manager',
                plugin='nav2_lifecycle_manager::LifecycleManager',
                name='lifecycle_manager_navigation',
                namespace=namespace,
                parameters=[{'autostart': autostart, 'node_names': lifecycle_nodes}],
            ),
            *[
                ComposableNode(
                    package=srv['package'],
                    plugin=srv['plugin'],
                    name=srv['name'],
                    namespace=namespace,
                    parameters=[configured_params],
                    remappings=remappings + ([('cmd_vel', 'cmd_vel_nav')] if srv['cmd_vel_remap'] else []),
                )
                for srv in active_servers
            ],
        ]
        actions.append(
            LoadComposableNodes(
                target_container=_container_full_name(namespace, container_name),
                composable_node_descriptions=composable_nodes,
            )
        )
    else:
        for srv in active_servers:
            actions.append(
                Node(
                    package=srv['package'],
                    executable=srv['executable'],
                    name=srv['name'],
                    namespace=namespace,
                    output='screen',
                    respawn=use_respawn,
                    respawn_delay=2.0,
                    parameters=[configured_params],
                    arguments=['--ros-args', '--log-level', log_level],
                    remappings=remappings + ([('cmd_vel', 'cmd_vel_nav')] if srv['cmd_vel_remap'] else []),
                )
            )
        actions.append(
            Node(
                package='nav2_lifecycle_manager',
                executable='lifecycle_manager',
                name='lifecycle_manager_navigation',
                namespace=namespace,
                output='screen',
                arguments=['--ros-args', '--log-level', log_level],
                parameters=[{'autostart': autostart}, {'node_names': lifecycle_nodes}],
            )
        )

    return [GroupAction(actions=actions)]


def generate_launch_description():
    smart_nav_dir = get_package_share_directory('smart_nav')
    default_params_file = os.path.join(smart_nav_dir, 'config', 'nav2_params.yaml')

    ld = LaunchDescription()
    ld.add_action(SetEnvironmentVariable('RCUTILS_LOGGING_BUFFERED_STREAM', '1'))

    ld.add_action(DeclareLaunchArgument(
        'namespace', default_value='', description='Top-level namespace'
    ))
    ld.add_action(DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation (Gazebo) clock if true',
    ))
    ld.add_action(DeclareLaunchArgument(
        'params_file',
        default_value=default_params_file,
        description='Full path to the ROS2 parameters file to use for all launched nodes',
    ))
    ld.add_action(DeclareLaunchArgument(
        'autostart',
        default_value='true',
        description='Automatically startup the nav2 stack',
    ))
    ld.add_action(DeclareLaunchArgument(
        'use_composition',
        default_value='True',
        description='Use composed bringup inside component_container_isolated if True',
    ))
    ld.add_action(DeclareLaunchArgument(
        'create_container',
        default_value='True',
        description='Launch nav2_container in this launch file when use_composition is True',
    ))
    ld.add_action(DeclareLaunchArgument(
        'container_name',
        default_value='nav2_container',
        description='Name of the component container when use_composition is True',
    ))
    ld.add_action(DeclareLaunchArgument(
        'use_docking',
        default_value='False',
        description='Enable opennav_docking (docking_server) and register it in lifecycle_manager',
    ))
    ld.add_action(DeclareLaunchArgument(
        'use_route',
        default_value='False',
        description='Enable nav2_route (route_server) and register it in lifecycle_manager',
    ))
    ld.add_action(DeclareLaunchArgument(
        'use_respawn',
        default_value='False',
        description='Whether to respawn if a node crashes. Applied when composition is disabled.',
    ))
    ld.add_action(DeclareLaunchArgument(
        'log_level', default_value='info', description='log level'
    ))

    ld.add_action(OpaqueFunction(function=_launch_navigation))
    return ld
