#!/bin/bash

SESSION="robot"

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

export CYCLONEDDS_URI=file:///home/oleksandr/cyclonedds.xml
ZENOH_CMD="zenoh-bridge-dds -l tcp/0.0.0.0:7447 --no-multicast-scouting \
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

tmux kill-session -t $SESSION 2>/dev/null
tmux new-session -d -s $SESSION

# --- ОКНО 0: Бессмертный агент ESP32-S3 по Native USB ---
tmux rename-window -t $SESSION:0 'MicroROS'
tmux send-keys -t $SESSION:0 "export CYCLONEDDS_URI=$CYCLONEDDS_URI" C-m
tmux send-keys -t $SESSION:0 'stty -F /dev/esp32s3 -hupcl' C-m
tmux send-keys -t $SESSION:0 'while true; do ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/esp32s3 -v4; sleep 2; done' C-m

# --- ОКНО 1: Железо и Инфраструктура ---
tmux new-window -t $SESSION:1 -n 'Hardware'
tmux send-keys -t $SESSION:1 "export CYCLONEDDS_URI=$CYCLONEDDS_URI" C-m
tmux send-keys -t $SESSION:1 'sleep 2' C-m
tmux send-keys -t $SESSION:1 'ros2 launch smart_master real_master.launch.py use_arm:=false' C-m

# --- ОКНО 2: Мост Zenoh (TCP туннель) ---
tmux new-window -t $SESSION:2 -n 'Zenoh_Bridge'
tmux send-keys -t $SESSION:2 "export CYCLONEDDS_URI=$CYCLONEDDS_URI" C-m
tmux send-keys -t $SESSION:2 "$ZENOH_CMD" C-m

echo " Робот успешно запущен в фоне!"
echo " Zenoh Bridge ожидает подключения на порту 7447"
echo " Для просмотра логов агента: tmux attach -t $SESSION"
echo " Для выхода из логов нажми Ctrl+B, затем D"

