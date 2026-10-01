#!/usr/bin/env python3
import numpy as np
import os
import json

def main():
    # Розмір карти
    width = 1200
    height = 800
    res = 0.05
    
    # Центр карти
    ox = -10.0
    oy = -10.0

    print(f"Generating physical map {width}x{height} ({width*res}x{height*res} meters)...")
    print(f"Map Origin: X={ox}, Y={oy}")

  # Коридор 012/7: "Радиационный слалом". Шахматное расположение кластеров.
    
    # Коридор 012/7: "Радиационный слалом" + макро-градиент
    # Интенсивность жестких источников снижена на 30%
    
    hard_splatters = [
        # --- КЛАСТЕР 1: Правый борт (Y: 5 - 10) ---
        {'x': 7.5, 'y': 5.0, 'intensity': 1700.0, 'size': 0.4, 'mu': 2.0},
        {'x': 8.0, 'y': 6.5, 'intensity': 1850.0, 'size': 0.5, 'mu': 1.8},
        {'x': 6.5, 'y': 7.5, 'intensity': 1900.0, 'size': 0.3, 'mu': 2.5},

        # --- КЛАСТЕР 2: Левый борт - Ловушка (Y: 11 - 15) ---
        {'x': 4.0, 'y': 10.8, 'intensity': 2400.0, 'size': 0.4, 'mu': 3.0},
        {'x': 5.0, 'y': 12.0, 'intensity': 2500.0, 'size': 0.5, 'mu': 3.5},
        {'x': 3.5, 'y': 12.2, 'intensity': 2800.0, 'size': 0.3, 'mu': 2.8},
        
        # --- КЛАСТЕР 3: Правый борт - Эпицентр (Y: 16 - 20) ---
        {'x': 7.5, 'y': 15.0, 'intensity': 4500.0, 'size': 0.25, 'mu': 1.2},
        {'x': 8.5, 'y': 16.5, 'intensity': 4800.0, 'size': 0.35, 'mu': 1.0},
        {'x': 6.5, 'y': 17.0, 'intensity': 4300.0, 'size': 0.2, 'mu': 1.5},

        # --- ФИНИШНАЯ ТОЧКА (Y: 21) ---
        {'x': 5.5, 'y': 21.0, 'intensity': 1800.0, 'size': 0.8, 'mu': 0.7}
    ]

    soft_clouds = [
        # --- МАКРО-ГРАДИЕНТ (Фон помещения) ---
        # Эпицентр фона находится в дальнем конце (Y = 22.0). 

        {'x': 2.0, 'y': 24.0, 'intensity': 540.0, 'sigma': 10.0},
        {'x': 15.0, 'y': 12.0, 'intensity': 250.0, 'sigma': 7.0},
        {'x': 0.0, 'y': 4.0, 'intensity': 120.0, 'sigma': 6.0},
        {'x': 8.0, 'y': 5.0, 'intensity': 250.0, 'sigma': 4.0},

    ]
           
        # Кластер 1: Эпицентр (Открытая лава ТСМ)
    #    {'x': 20.0, 'y': 15.0, 'intensity': 5000.0, 'size': 1.1, 'mu': 0.65},
    #    {'x': 19.5, 'y': 15.8, 'intensity': 3600.0, 'size': 1.1, 'mu': 0.50},
    #    {'x': 21.0, 'y': 14.5, 'intensity': 3000.0, 'size': 1.3, 'mu': 0.75},
    #    {'x': 20.2, 'y': 14.0, 'intensity': 4200.0, 'size': 1.3, 'mu': 0.60},
    #    {'x': 18.5, 'y': 16.0, 'intensity': 3300.0, 'size': 1.2, 'mu': 0.95},
        
        # Кластер 2: Ловушка (ТСМ под наплывом бетона)
    #    {'x': 35.0, 'y': 5.0, 'intensity': 2500.0, 'size': 2.2, 'mu': 1.1},
    #    {'x': 35.5, 'y': 5.5, 'intensity': 1900.0, 'size': 1.9, 'mu': 1.2},
    ##    {'x': 34.5, 'y': 4.8, 'intensity': 1800.0, 'size': 1.8, 'mu': 1.4},
    # #   {'x': 36.0, 'y': 4.0, 'intensity': 2200.0, 'size': 2.1, 'mu': 1.1},
        
        # Кластер 3: Россыпь (Гравий и обломки труб у входа)
    #    {'x': 5.0,  'y': 20.0, 'intensity': 1600.0, 'size': 1.2, 'mu': 0.6},
    #    {'x': 6.5,  'y': 19.0, 'intensity': 1200.0, 'size': 1.0, 'mu': 0.9},
    #    {'x': 4.0,  'y': 21.5, 'intensity': 950.0,  'size': 0.8, 'mu': 0.85},
    #    {'x': 7.0,  'y': 22.0, 'intensity': 550.0,  'size': 0.7, 'mu': 1.0},
    #    {'x': 3.5,  'y': 18.5, 'intensity': 1400.0, 'size': 1.1, 'mu': 0.9},
    #    {'x': 8.0,  'y': 19.5, 'intensity': 1100.0, 'size': 1.0, 'mu': 0.95},

        # Кластер 4: Дальнобойная радиация (широкий градиент, очень слабое затухание)
    #    {'x': 10.0, 'y': 5.0,  'intensity': 900.0,  'size': 3.0, 'mu': 0.15},
    #    {'x': 40.0, 'y': 25.0, 'intensity': 1200.0, 'size': 4.0, 'mu': 0.1},
        
        # Кластер 5: Микро-спайки (очень резкие локальные экстремумы, огромное затухание)
    #    {'x': 15.0, 'y': 25.0, 'intensity': 8500.0, 'size': 0.5, 'mu': 4.5},
    #    {'x': 25.0, 'y': 10.0, 'intensity': 7500.0, 'size': 0.4, 'mu': 5.0},
    #    {'x': 45.0, 'y': 15.0, 'intensity': 8000.0, 'size': 0.6, 'mu': 3.8}
    #]

    #soft_clouds = [
    #    # Фоновые облака (Диффузный фон, покрывающий всю комнату)
    #    {'x': 20.0, 'y': 10.0, 'intensity': 150.0, 'sigma': 15.0},
    #    {'x': 10.0, 'y': 25.0, 'intensity': 100.0, 'sigma': 20.0},
    #    {'x': 35.0, 'y': 20.0, 'intensity': 200.0, 'sigma': 12.0},
    #    {'x': 0.0,  'y': 5.0,  'intensity': 120.0, 'sigma': 18.0}
    #]

    x = np.linspace(0, width - 1, width) * res + ox
    y = np.linspace(0, height - 1, height) * res + oy
    xv, yv = np.meshgrid(x, y)

    total_dose = np.zeros((height, width), dtype=np.float32)

    np.random.seed(42) # Фиксируем сид для одинаковых уникальных форм при каждом запуске

    for src in hard_splatters:
        dx = xv - src['x']
        dy = yv - src['y']
        
        # Создаем естественную эллиптическую форму, а не звезду
        theta = np.random.uniform(0, np.pi)
        scale_x = np.random.uniform(0.7, 1.4)
        scale_y = np.random.uniform(0.7, 1.4)
        
        # Поворачиваем координаты для наклона эллипса
        dx_rot = dx * np.cos(theta) - dy * np.sin(theta)
        dy_rot = dx * np.sin(theta) + dy * np.cos(theta)
        
        # Эллиптическое расстояние
        dist = np.sqrt((dx_rot * scale_x)**2 + (dy_rot * scale_y)**2)
        
        # Очень плавная, низкочастотная деформация (никаких резких углов)
        angle = np.arctan2(dy_rot, dx_rot)
        noise = 1.0 + np.random.uniform(0.02, 0.08) * np.sin(2.0 * angle + np.random.uniform(0, 2 * np.pi))
        
        r_effective = dist * noise
        r_core = src['size']
        
        dose = (src['intensity'] / ((r_effective / r_core)**2 + 1.0)) * np.exp(-src['mu'] * r_effective)
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
    
    # 1. NPY
    npy_filename = os.path.join(save_dir, 'radiation_map_complex.npy')
    np.save(npy_filename, total_dose)
    
    # 2. JSON 
    meta = {
        "width": width,
        "height": height,
        "res": res,
        "ox": ox,
        "oy": oy
    }
    json_filename = os.path.join(save_dir, 'radiation_map_complex_meta.json')
    with open(json_filename, 'w') as f:
        json.dump(meta, f, indent=4)
        
    print(f"Done! Saved NPY to {npy_filename}")
    print(f"Saved META JSON to {json_filename}")
    print(f"Maximum dose: {np.max(total_dose):.2f} mSv/h")

if __name__ == '__main__':
    main()