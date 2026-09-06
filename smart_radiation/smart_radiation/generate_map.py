#!/usr/bin/env python3
import numpy as np
import os
import json

def main():
    # Увеличиваем размер карты до 40x40 метров, чтобы покрыть всю возможную зону SLAM (Room 213 и т.д.)
    # Это предотвратит "резкие обрывы" по краям карты.
    width = 1200
    height = 800
    res = 0.05
    
    # Смещаем центр (Origin), чтобы покрыть диапазон до X=20, Y=30
    # X будет от -10 до 50. Y будет от -10 до 30.
    ox = -10.0
    oy = -10.0
    mu_air = 0.9  

    print(f"Generating physical map {width}x{height} ({width*res}x{height*res} meters)...")
    print(f"Map Origin: X={ox}, Y={oy}")

    # Внимание: координаты здесь теперь - это РЕАЛЬНЫЕ мировые координаты SLAM
    # Если раньше старая кривая система координат сдвигала все на -5 по X и -4.6 по Y,
    # то теперь X=5.6 будет реально на X=5.6 в SLAM.
    hard_splatters = [
        {'x': 2.0,  'y': -2.0,  'intensity': 1500.0, 'size': 1.2},
        {'x': 8.5, 'y': 0.0, 'intensity': 900.0, 'size': 0.8},
        {'x': 3.6,  'y': 0.4,  'intensity': 700.0, 'size': 0.5},
        {'x': -3.0,  'y': 0.0,  'intensity': 800.0, 'size': 0.7}
    
    
    #    {'x': 5.5,  'y': 22.0,  'intensity': 3000.0, 'size': 1.0},
    #    {'x': 10.0, 'y': 8.0, 'intensity': 5500.0, 'size': 1.6},
    #    {'x': 8.0,  'y': 16.0,  'intensity': 3500.0, 'size': 0.8},
    #    {'x': 2.0,  'y': 2.0,  'intensity': 2500.0, 'size': 0.7}
    #    {'x': 5.6,  'y': 4.4,  'intensity': 5000.0, 'size': 1.45},
    #    {'x': -3.5, 'y': -3.1, 'intensity': 3000.0, 'size': 0.7},
    #    {'x': 2.9,  'y': 8.9,  'intensity': 4000.0, 'size': 1.0},
    #    {'x': 6.5,  'y': 7.9,  'intensity': 2500.0,4 'size': 0.9},
    #    {'x': 0.0,  'y': 4.7,  'intensity': 3000.0, 'size': 0.75},
    #    {'x': 2.5,  'y': -4.1, 'intensity': 2500.0, 'size': 0.5},
    #    {'x': -2.8, 'y': 7.4,  'intensity': 3500.0, 'size': 0.8}
    ]

    soft_clouds = [
        {'x': -3.0, 'y': 1.4,  'intensity': 180.0, 'sigma': 2.5},
        {'x': -1.0, 'y': -2.6, 'intensity': 125.0, 'sigma': 2.8}, 
        {'x': 10.0, 'y': 15.0, 'intensity': 100.0, 'sigma': 4.0},
        {'x': 15.0, 'y': 25.0, 'intensity': 150.0, 'sigma': 3.5},
        {'x': 5.0,  'y': 28.0, 'intensity': 80.0, 'sigma': 3.0},
        {'x': 18.0, 'y': 5.0,  'intensity': 125.0, 'sigma': 4.5},
        {'x': 5.0,  'y': 5.0,  'intensity': 150.0, 'sigma': 3.5} 
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

    from ament_index_python.packages import get_package_share_directory
    
    pkg_share = get_package_share_directory('smart_radiation')
    src_dir = pkg_share.replace('install/smart_radiation/share/smart_radiation', 'src/smart_robotics/smart_radiation')
    save_dir = os.path.join(src_dir, 'maps')
    os.makedirs(save_dir, exist_ok=True)
    
    # 1. Сохраняем NPY
    npy_filename = os.path.join(save_dir, 'radiation_map.npy')
    np.save(npy_filename, total_dose)
    
    # 2. Сохраняем JSON (ОЧЕНЬ ВАЖНО ДЛЯ virtual_geiger)
    meta = {
        "width": width,
        "height": height,
        "res": res,
        "ox": ox,
        "oy": oy
    }
    json_filename = os.path.join(save_dir, 'radiation_map_meta.json')
    with open(json_filename, 'w') as f:
        json.dump(meta, f, indent=4)
        
    print(f"Done! Saved NPY to {npy_filename}")
    print(f"Saved META JSON to {json_filename}")
    print(f"Maximum dose: {np.max(total_dose):.2f} mSv/h")

if __name__ == '__main__':
    main()