#!/usr/bin/env python3
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
import os
from ament_index_python.packages import get_package_share_directory # Import gor dynamically finding the package share directory

# Dynamically find the package share directory
pkg_share = get_package_share_directory('smart_radiation')
fallback_path = os.path.join(pkg_share, 'maps', 'radiation_map.npy')

# Hardpath if required (uncomment the following line and comment the above two lines)
# fallback_path = os.path.expanduser('~/ros2_ws/src/smart_robotics/smart_radiation/maps/radiation_map.npy')

if os.path.exists(fallback_path):
    filename = fallback_path
else:
    print(f"Error: File {fallback_path} not found. Please run generate_map.py first!")
    exit()

dose_map = np.load(filename)

res = 0.05
ox = -5.0024
oy = -4.63
height, width = dose_map.shape

extent = [ox, ox + width * res, oy, oy + height * res]

fig = plt.figure(figsize=(16, 6))
fig.canvas.manager.set_window_title('ALARA Map Analyzer (Strict 100% Sync with ROS)')

ax_phys = fig.add_subplot(131)
ax_cost = fig.add_subplot(132)
ax_graph = fig.add_subplot(133)
plt.subplots_adjust(bottom=0.25, wspace=0.3)

img_phys = ax_phys.imshow(dose_map, cmap='hot', origin='lower', extent=extent)
ax_phys.set_title("Raw Physics (mSv/h)")
ax_phys.set_xlabel("X (meters)")
ax_phys.set_ylabel("Y (meters)")
fig.colorbar(img_phys, ax=ax_phys, fraction=0.046, pad=0.04)

def calc_costmap(d_map, d_noise, d_crit, k):
    cost_field = np.zeros_like(d_map)
    
    if d_crit <= d_noise:
        d_crit = d_noise + 0.1 
        
    mask = (d_map > d_noise) & (d_map < d_crit)
    
    norm = (d_map[mask] - d_noise) / (d_crit - d_noise)
    norm = np.clip(norm, 0.0, 1.0)
    
    center = 0.5
    min_sig = 1.0 / (1.0 + np.exp(-k * (0.0 - center)))
    max_sig = 1.0 / (1.0 + np.exp(-k * (1.0 - center)))
    raw_sig = 1.0 / (1.0 + np.exp(-k * (norm - center)))
    
    penalty_100 = 100.0 * (raw_sig - min_sig) / (max_sig - min_sig)
    
    cost_field[mask] = penalty_100
    cost_field[d_map >= d_crit] = 100.0 
    
    if isinstance(d_map, np.ndarray):
        grid_100 = np.round(cost_field).astype(int)
    else:
        grid_100 = int(np.round(cost_field))
        
    final_cost = (grid_100 * 252) // 100
    
    return final_cost

init_noise = 5.0
init_crit = 500.0
init_k = 5.0

cost_map = calc_costmap(dose_map, init_noise, init_crit, init_k)
img_cost = ax_cost.imshow(cost_map, cmap='turbo', origin='lower', extent=extent, vmin=0, vmax=252)
ax_cost.set_title("Costmap (C++ Plugin: 0-252)")
ax_cost.set_xlabel("X (meters)")
fig.colorbar(img_cost, ax=ax_cost, fraction=0.046, pad=0.04)

x_val = np.linspace(0, init_crit * 1.2, 500)
y_val = calc_costmap(x_val, init_noise, init_crit, init_k) 
line, = ax_graph.plot(x_val, y_val, 'b-', lw=2.5)
ax_graph.axhline(253, color='r', linestyle='--', alpha=0.5, label='Barrier (253)')
ax_graph.set_title("Penalty Function C_rad(D)")
ax_graph.set_xlabel("Dose (mSv/h)")
ax_graph.set_ylabel("Nav2 Penalty (0-253)")
ax_graph.set_xlim(0, init_crit * 1.2)
ax_graph.set_ylim(-10, 265)
ax_graph.legend()
ax_graph.grid(True, alpha=0.3)

def on_hover(event):
    if event.inaxes in [ax_phys, ax_cost]:
        real_x = event.xdata
        real_y = event.ydata
        
        x_idx = int((real_x - ox) / res)
        y_idx = int((real_y - oy) / res)
        
        if 0 <= y_idx < height and 0 <= x_idx < width:
            dose = dose_map[y_idx, x_idx]
            cost = cost_map[y_idx, x_idx]
            fig.canvas.toolbar.set_message(f"X: {real_x:.2f}m, Y: {real_y:.2f}m | Dose: {dose:.2f} mSv/h | Penalty: {cost}")

fig.canvas.mpl_connect('motion_notify_event', on_hover)

axcolor = 'lightgoldenrodyellow'
ax_noise = plt.axes([0.15, 0.15, 0.65, 0.03], facecolor=axcolor)
ax_crit  = plt.axes([0.15, 0.10, 0.65, 0.03], facecolor=axcolor)
ax_k     = plt.axes([0.15, 0.05, 0.65, 0.03], facecolor=axcolor)

s_noise = Slider(ax_noise, 'Background (D_noise)', 0.1, 100.0, valinit=init_noise)
s_crit  = Slider(ax_crit, 'Death (D_crit)', 100.0, 5000.0, valinit=init_crit)
s_k     = Slider(ax_k, 'Curvature (K)', 1.0, 15.0, valinit=init_k)

def update(val):
    global cost_map
    d_n = s_noise.val
    d_c = s_crit.val
    k_v = s_k.val
    
    cost_map = calc_costmap(dose_map, d_n, d_c, k_v)
    img_cost.set_data(cost_map)
    
    x_new = np.linspace(0, d_c * 1.2, 500)
    y_new = calc_costmap(x_new, d_n, d_c, k_v) 
    
    line.set_data(x_new, y_new)
    ax_graph.set_xlim(0, d_c * 1.2)
    fig.canvas.draw_idle()

s_noise.on_changed(update)
s_crit.on_changed(update)
s_k.on_changed(update)

plt.show()