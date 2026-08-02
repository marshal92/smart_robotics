#!/bin/bash

SESSION="smart_server"
IP_ROBOTA="192.168.31.100" # Проверь, чтобы был актуальный

tmux kill-session -t $SESSION 2>/dev/null
tmux new-session -d -s $SESSION

# Формируем команду Zenoh
ZENOH_CMD="zenoh-bridge-dds -e tcp/$IP_ROBOTA:7447 --no-multicast-scouting \
\
--allow '^rt/cmd_vel$' \
--allow '^rt/cmd_light$' \
--allow '^rt/smart_command$' \
--allow '^rt/initialpose$' \
--allow '^rt/goal_pose$' \
--allow '^rt/clicked_point$' \
\
--allow '^rt/smart_telemetry$' \
--allow '^rt/operator_heartbeat$' \
--allow '^rt/waypoints_list$' \
--allow '^rt/smart_waypoints_markers$' \
\
--allow '^rt/tf$' \
--allow '^rt/tf_static$' \
--allow '^rt/odom$' \
--allow '^rt/robot_description$' \
--allow '^rt/map$' \
--allow '^rt/map_updates$' \
--allow '^rt/radiation_map$' \
--allow '^rt/radiation_image/compressed$' \
--allow '^rt/camera/image_raw/compressed$' \
--allow '^rt/plan$' \
\
--allow '^rt/rosout$'"

# --allow '^rt/scan$' \
# --allow '^rt/odom$' \
# --allow '^rt/fsm_status$'\
# --allow '^rt/current_dose_rate$' \
# --allow '^rt/payload/.*' \
# --allow '^rt/global_costmap/costmap$' \
# --allow '^rt/global_costmap/costmap_updates$' \
# --allow '^rt/local_costmap/costmap$' \
# --allow '^rt/local_costmap/costmap_updates$' \
# --allow '^rt/waypoint
# --allow '^rt/operator_command$' \
# --allow '^rt/system_command$' \
# --allow '^rt/tactical_command$' \
# --allow '^rt/navigate_through_poses/.*' \
# --allow '^rq/navigate_through_poses/.*' \
# --allow '^rr/navigate_through_poses/.*' \

# Окно 0: Zenoh Bridge (Связь с роботом)
tmux rename-window -t $SESSION:0 'Zenoh_Client'
tmux send-keys -t $SESSION:0 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' C-m
tmux send-keys -t $SESSION:0 "$ZENOH_CMD" C-m

# Окно 1: ROSBridge (Для твоего HTML-интерфейса)
#tmux new-window -t $SESSION:1 -n 'ROS_Bridge'
#tmux send-keys -t $SESSION:1 'source /opt/ros/jazzy/setup.bash' C-m
#tmux send-keys -t $SESSION:1 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' C-m
#tmux send-keys -t $SESSION:1 'ros2 run rosbridge_server rosbridge_websocket' C-m

# Окно 2: Твои локальные узлы (Оркестратор, Тень и т.д.)
tmux new-window -t $SESSION:2 -n 'Master_Launch'
tmux send-keys -t $SESSION:2 'source ~/ros2_ws/install/setup.bash' C-m
tmux send-keys -t $SESSION:2 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' C-m
tmux send-keys -t $SESSION:2 'sleep 2' C-m
tmux send-keys -t $SESSION:2 'ros2 launch smart_server server.launch.py' C-m

echo " Серверная станция запущена!"
echo " Web интерфейс доступен"
echo " Логи сервера: tmux attach -t $SESSION"
