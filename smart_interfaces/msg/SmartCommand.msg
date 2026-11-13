# Target subsystem (e.g., "system", "nav", "payload", "waypoints")
string target_system

# Command name (e.g., "start", "stop", "go_to", "rth", "save")
string command

# Additional payload data (coordinates X, Y, Yaw or waypoint name encoded as JSON)
# Send an empty string "" when no additional payload is required
string payload_json