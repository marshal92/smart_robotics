# Кому адресован приказ (например: "system", "nav", "payload", "waypoints")
string target_system

# Сама команда (например: "start", "stop", "go_to", "rth", "save")
string command

# Дополнительные данные (координаты X, Y, Yaw или имя точки, упакованные в JSON)
# Если доп. данных нет, шлем пустую строку ""
string payload_json