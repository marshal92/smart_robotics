#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.distance import cdist

try:
    from mcap_ros2.reader import read_ros2_messages
except ImportError:
    print("Error: Activate virtualenv first: source mppi_env/bin/activate")
    exit(1)

# SET MCAP FILE NAME FOR ACCURACY TEST
mcap_file_path = "test10_0.mcap" 

odom_data = []
plan_data = []

print("Reading MCAP file...")
with open(mcap_file_path, "rb") as f:
    for msg in read_ros2_messages(f):
        topic = msg.channel.topic
        ros_msg = msg.ros_msg
        
        if topic == "/odom":
            odom_data.append([ros_msg.pose.pose.position.x, ros_msg.pose.pose.position.y])
        elif topic == "/plan" and not plan_data:
            # Capture the initial global plan
            plan_data = [[pose.pose.position.x, pose.pose.position.y] for pose in ros_msg.poses]

df_odom = pd.DataFrame(odom_data, columns=['x', 'y'])
raw_plan_coords = np.array(plan_data)

if df_odom.empty or len(raw_plan_coords) == 0:
    print("Error: Missing /odom or /plan data")
    exit(1)

# COMPENSATE TF OFFSET (map -> odom)
print("Compensating TF offset...")
# Compute offset between initial odometry and start of the plan
offset = df_odom[['x', 'y']].iloc[0].values - raw_plan_coords[0]
# Align plan with actual trajectory
aligned_plan_coords = raw_plan_coords + offset

# COMPUTE CROSS-TRACK ERROR (CTE)
print("Computing Cross-Track Error (CTE)...")
odom_coords = df_odom[['x', 'y']].values
distances = cdist(odom_coords, aligned_plan_coords)
df_odom['cte'] = np.min(distances, axis=1)

# Error metrics
rmse_cte = np.sqrt(np.mean(df_odom['cte']**2))
max_cte = df_odom['cte'].max()
mean_cte = df_odom['cte'].mean()

print("\n=== KINEMATIC TRACKING ACCURACY RESULTS ===")
print(f"Mean CTE: {mean_cte*1000:.2f} mm")
print(f"Max CTE:  {max_cte*1000:.2f} mm")
print(f"RMSE CTE: {rmse_cte*1000:.2f} mm")
print("===========================================\n")

# Plot comparison
plt.rcParams.update({'font.size': 12})
fig, ax = plt.subplots(figsize=(10, 6))

ax.plot(aligned_plan_coords[:, 0], aligned_plan_coords[:, 1], 'g--', linewidth=2.5, label='Global plan (TF-aligned)')
ax.plot(df_odom['x'], df_odom['y'], 'b-', linewidth=2, alpha=0.8, label='Actual trajectory (/odom)')

ax.set_title('Kinematic Path-Following Accuracy', fontweight='bold')
ax.set_xlabel('X Coordinate (m)')
ax.set_ylabel('Y Coordinate (m)')
ax.grid(True, linestyle='--', alpha=0.7)
ax.legend()
ax.axis('equal') # Preserve true aspect ratio

plt.tight_layout()
plt.savefig("accuracy_test_plot_final.png", dpi=300)
print("Saved plot: accuracy_test_plot_final.png")