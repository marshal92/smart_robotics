#!/bin/bash

SESSION="robot"

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

export CYCLONEDDS_URI=file:///home/oleksandr/cyclonedds.xml
ZENOH_CMD="zenoh-bridge-dds -l tcp/0.0.0.0:7447 --no-multicast-scouting \
--allow '^rt/map$' \
--allow '^rt/map_updates$' \
--allow '^rt/tf$' \
--allow '^rt/tf_static$' \
--allow '^rt/odom$' \
--allow '^rt/robot_description$' \
--allow '^rt/rosout$' \
--allow '^rt/plan$' \
--allow '^rt/goal_pose$' \
--allow '^rt/initialpose$' \
--allow '^rt/clicked_point$' \
--allow '^rt/cmd_vel$' \
--allow '^rt/cmd_light$' \
--allow '^rt/system_command$' \
--allow '^rt/tactical_command$' \
--allow '^rt/operator_command$' \
--allow '^rt/operator_heartbeat$' \
--allow '^rt/current_dose_rate$' \
--allow '^rt/radiation_map$' \
--allow '^rt/camera/image_raw/compressed$' \
--allow '^rt/global_costmap/costmap$' \
--allow '^rt/global_costmap/costmap_updates$' \
--allow '^rt/local_costmap/costmap$' \
--allow '^rt/local_costmap/costmap_updates$' \
--allow '^rt/navigate_through_poses/.*' \
--allow '^rq/navigate_through_poses/.*' \
--allow '^rr/navigate_through_poses/.*' \
--allow '^rq/global_costmap/.*' \
--allow '^rr/global_costmap/.*' \
--allow '^rq/local_costmap/.*' \
--allow '^rr/local_costmap/.*'"

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
tmux send-keys -t $SESSION:1 'ros2 launch fcm_digital_twin hardware_bringup.launch.py' C-m
#tmux send-keys -t $SESSION:1 'ros2 launch smart_master real_master.launch.py use_arm:=false' C-m

# --- ОКНО 2: Мост Zenoh (TCP туннель) ---
tmux new-window -t $SESSION:2 -n 'Zenoh_Bridge'
tmux send-keys -t $SESSION:2 "export CYCLONEDDS_URI=$CYCLONEDDS_URI" C-m
tmux send-keys -t $SESSION:2 "$ZENOH_CMD" C-m

echo " Робот успешно запущен в фоне!"
echo " Zenoh Bridge ожидает подключения на порту 7447"
echo " Для просмотра логов агента: tmux attach -t $SESSION"
echo " Для выхода из логов нажми Ctrl+B, затем D"

