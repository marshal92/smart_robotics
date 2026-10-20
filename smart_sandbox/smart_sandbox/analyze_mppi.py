#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.distance import cdist

try:
    from mcap_ros2.reader import read_ros2_messages
except ImportError:
    print("Помилка: Активуйте venv: source mppi_env/bin/activate")
    exit(1)

# ВКАЖІТЬ НАЗВУ ФАЙЛУ ДЛЯ ТЕСТУ ТОЧНОСТІ
mcap_file_path = "test10_0.mcap" 

odom_data = []
plan_data = []

print("Читання MCAP файлу...")
with open(mcap_file_path, "rb") as f:
    for msg in read_ros2_messages(f):
        topic = msg.channel.topic
        ros_msg = msg.ros_msg
        
        if topic == "/odom":
            odom_data.append([ros_msg.pose.pose.position.x, ros_msg.pose.pose.position.y])
        elif topic == "/plan" and not plan_data:
            # Беремо справжній перший план
            plan_data = [[pose.pose.position.x, pose.pose.position.y] for pose in ros_msg.poses]

df_odom = pd.DataFrame(odom_data, columns=['x', 'y'])
raw_plan_coords = np.array(plan_data)

if df_odom.empty or len(raw_plan_coords) == 0:
    print("Помилка: Немає даних /odom або /plan")
    exit(1)

# КОМПЕНСАЦІЯ TF ЗСУВУ (map -> odom)
print("Компенсація TF зсуву...")
# Знаходимо різницю між початком одометрії та початком плану
offset = df_odom[['x', 'y']].iloc[0].values - raw_plan_coords[0]
# Суміщаємо план з фактичною траєкторією
aligned_plan_coords = raw_plan_coords + offset

# РОЗРАХУНОК ЧЕСНОГО CTE
print("Розрахунок похибки (CTE)...")
odom_coords = df_odom[['x', 'y']].values
distances = cdist(odom_coords, aligned_plan_coords)
df_odom['cte'] = np.min(distances, axis=1)

# Математичні метрики
rmse_cte = np.sqrt(np.mean(df_odom['cte']**2))
max_cte = df_odom['cte'].max()
mean_cte = df_odom['cte'].mean()

print("\n=== ЧЕСНІ РЕЗУЛЬТАТИ КІНЕМАТИЧНОЇ ТОЧНОСТІ ===")
print(f"Середня похибка (Mean CTE): {mean_cte*1000:.2f} мм")
print(f"Максимальне відхилення (Max CTE): {max_cte*1000:.2f} мм")
print(f"Середньоквадратичне відхилення (RMSE): {rmse_cte*1000:.2f} мм")
print("===============================================\n")

# Побудова графіка
plt.rcParams.update({'font.size': 12})
fig, ax = plt.subplots(figsize=(10, 6))

ax.plot(aligned_plan_coords[:, 0], aligned_plan_coords[:, 1], 'g--', linewidth=2.5, label='Глобальний план (із компенсацією TF)')
ax.plot(df_odom['x'], df_odom['y'], 'b-', linewidth=2, alpha=0.8, label='Фактична траєкторія (/odom)')

ax.set_title('Кінематична точність відпрацювання маршруту', fontweight='bold')
ax.set_xlabel('Координата X (м)')
ax.set_ylabel('Координата Y (м)')
ax.grid(True, linestyle='--', alpha=0.7)
ax.legend()
ax.axis('equal') # Зберігає реальні пропорції

plt.tight_layout()
plt.savefig("accuracy_test_plot_final.png", dpi=300)
print("Графік збережено: accuracy_test_plot_final.png")