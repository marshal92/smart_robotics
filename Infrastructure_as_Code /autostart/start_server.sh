#!/bin/bash

SESSION="smart_server"
IP_ROBOTA="192.168.31.100"
USE_ARM=${1:-false}

tmux kill-session -t $SESSION 2>/dev/null
tmux new-session -d -s $SESSION

# Build Zenoh bridge command
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

# Window 0: Zenoh Bridge (Connection to robot)
tmux rename-window -t $SESSION:0 'Zenoh_Client'
tmux send-keys -t $SESSION:0 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' C-m
tmux send-keys -t $SESSION:0 "$ZENOH_CMD" C-m

# Window 2: Local server nodes (Orchestrator, Shadow, Web UI, etc.)
tmux new-window -t $SESSION:2 -n 'Master_Launch'
tmux send-keys -t $SESSION:2 'source ~/ros2_ws/install/setup.bash' C-m
tmux send-keys -t $SESSION:2 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' C-m
tmux send-keys -t $SESSION:2 'sleep 2' C-m
tmux send-keys -t $SESSION:2 "ros2 launch smart_server server.launch.py use_arm:=$USE_ARM" C-m

echo "Server station started (use_arm=$USE_ARM)!"
echo "Web interface is available on port 8080"
echo "Server logs: tmux attach -t $SESSION"
