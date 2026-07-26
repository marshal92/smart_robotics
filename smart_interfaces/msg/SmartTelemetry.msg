std_msgs/Header header

# Статусы систем
string fsm_state           # "NORMAL", "WARNING", "EVACUATING"
string nav_status          # "IDLE", "MOVING", "ARRIVED"

# Локомоция
float32 linear_speed       # m/s
float32 angular_speed      # rad/s

# Полезная нагрузка и среда
float32 dose_rate          # uSv/h
bool light_is_on           # Состояние фонаря
string[] active_tools      # Список активных инструментов (например, ["lfcm_drill"])

# На будущее
float32 battery_voltage    # V