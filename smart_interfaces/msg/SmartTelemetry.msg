std_msgs/Header header

# System states
string fsm_state           # "NORMAL", "WARNING", "EVACUATING"
string nav_status          # "IDLE", "MOVING", "ARRIVED"

# Locomotion
float32 linear_speed       # m/s
float32 angular_speed      # rad/s

# Payload and environment
float32 dose_rate          # uSv/h
bool light_is_on           # Headlight relay state
string[] active_tools      # List of active tools (e.g., ["lfcm_drill"])

# Reserved for future use
float32 battery_voltage    # V