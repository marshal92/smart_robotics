#!/usr/bin/env python3
import numpy as np
import os

def main():
    # Native parameters: exactly 15 by 15 meters
    width = 300
    height = 300
    res = 0.05
    
    ox = 0.0
    oy = 0.0
    mu_air = 0.9  

    print(f"Generating physical map {width}x{height} ({width*res}x{height*res} meters)...")

    hard_splatters = [
        {'x': 10.6, 'y': 9.0,  'intensity': 5000.0, 'size': 1.45},
        {'x': 1.5,  'y': 1.5,  'intensity': 3000.0, 'size': 0.7},
        {'x': 7.9,  'y': 13.5, 'intensity': 4000.0, 'size': 1.0},
        {'x': 11.5, 'y': 12.5, 'intensity': 2500.0, 'size': 0.9},
        {'x': 5.0,  'y': 9.3,  'intensity': 3000.0, 'size': 0.75},
        {'x': 7.5,  'y': 0.5,  'intensity': 2500.0, 'size': 0.5},
        {'x': 2.2,  'y': 12.0, 'intensity': 3500.0, 'size': 0.8}
    ]

    soft_clouds = [
        {'x': 2.0,  'y': 6.0,  'intensity': 180.0, 'sigma': 2.5},
        {'x': 4.0,  'y': 2.0,  'intensity': 225.0, 'sigma': 2.8}, 
        {'x': 8.0,  'y': 8.0,  'intensity': 120.0, 'sigma': 2.0},
        {'x': 6.0,  'y': 14.0, 'intensity': 150.0, 'sigma': 3.0},
        {'x': 13.0, 'y': 13.0, 'intensity': 150.0, 'sigma': 2.5},
        {'x': 12.0, 'y': 2.0,  'intensity': 225.0, 'sigma': 2.8} 
    ]

    x = np.linspace(0, width - 1, width) * res + ox
    y = np.linspace(0, height - 1, height) * res + oy
    xv, yv = np.meshgrid(x, y)

    total_dose = np.zeros((height, width), dtype=np.float32)

    for src in hard_splatters:
        dx = xv - src['x']
        dy = yv - src['y']
        dist = np.sqrt(dx**2 + dy**2)
        
        angle = np.arctan2(dy, dx)
        noise = 1.0 + 0.1 * np.sin(3.0 * angle) + 0.05 * np.cos(5.0 * angle)
        r_effective = dist * noise
        r_core = src['size']
        
        dose = (src['intensity'] / ((r_effective / r_core)**2 + 1.0)) * np.exp(-mu_air * r_effective)
        total_dose += dose

    for cloud in soft_clouds:
        dist_sq = (xv - cloud['x'])**2 + (yv - cloud['y'])**2
        dose = cloud['intensity'] * np.exp(-dist_sq / (2 * cloud['sigma']**2))
        total_dose += dose

    total_dose += 0.05 

    # Dynamically find the save directory relative to the script
    # This will find the src/smart_robotics/smart_radiation/maps folder regardless of the workspace name
    script_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.abspath(os.path.join(script_dir, '..', 'maps'))

    # Hardpath if required (uncomment the following line and comment the above two lines)
    # save_dir = os.path.expanduser('~/ros2_ws/src/smart_robotics/smart_radiation/maps')
    
    os.makedirs(save_dir, exist_ok=True)
    filename = os.path.join(save_dir, 'radiation_map.npy')
    
    np.save(filename, total_dose)
    print(f"Done! Saved to {filename}")
    print(f"Maximum dose: {np.max(total_dose):.2f} mSv/h")

if __name__ == '__main__':
    main()