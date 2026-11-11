#!/bin/bash

SESSION="robot"
USE_ARM=${1:-false}

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
--allow '^rt/robot_description$' \
--allow '^rt/map$' \
--allow '^rt/map_updates$' \
--allow '^rt/radiation_map$' \
--allow '^rt/radiation_image/compressed$' \
--allow '^rt/radiation/status$' \
--allow '^rt/camera/image_raw/compressed$' \
--allow '^rt/plan$' \
--allow '^rt/arm_joint_states$' \
--allow '^rt/arm_controller/joint_trajectory$' \
--allow '^.*/arm_controller/follow_joint_trajectory/.*$' \
\
--allow '^rt/rosout$'"

tmux kill-session -t $SESSION 2>/dev/null
tmux new-session -d -s $SESSION

# Window 0: Persistent ESP32-S3 micro-ROS agent over Native USB
tmux rename-window -t $SESSION:0 'MicroROS'
tmux send-keys -t $SESSION:0 "export CYCLONEDDS_URI=$CYCLONEDDS_URI" C-m
tmux send-keys -t $SESSION:0 'stty -F /dev/esp32s3 -hupcl' C-m
tmux send-keys -t $SESSION:0 'while true; do ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/esp32s3 -v4; sleep 2; done' C-m

# Window 1: Hardware and Control Infrastructure
tmux new-window -t $SESSION:1 -n 'Hardware'
tmux send-keys -t $SESSION:1 "export CYCLONEDDS_URI=$CYCLONEDDS_URI" C-m
tmux send-keys -t $SESSION:1 'source /opt/ros/jazzy/setup.bash && source ~/ros2_ws/install/setup.bash' C-m
tmux send-keys -t $SESSION:1 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' C-m
tmux send-keys -t $SESSION:1 'sleep 2' C-m
tmux send-keys -t $SESSION:1 "ros2 launch smart_master real_master.launch.py use_arm:=$USE_ARM" C-m

# Window 2: Zenoh Bridge (TCP tunnel)
tmux new-window -t $SESSION:2 -n 'Zenoh_Bridge'
tmux send-keys -t $SESSION:2 "export CYCLONEDDS_URI=$CYCLONEDDS_URI" C-m
tmux send-keys -t $SESSION:2 "$ZENOH_CMD" C-m

echo "Robot started in background (use_arm=$USE_ARM)!"
echo "Zenoh Bridge listening on port 7447"
echo "Attach to logs: tmux attach -t $SESSION"
