#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# Настройки графиков для научных журналов Q1 (имитация LaTeX/Times New Roman)
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"], # Шрифты с засечками
    "font.size": 12,
    "axes.labelsize": 14,
    "axes.titlesize": 14,
    "legend.fontsize": 10,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "lines.linewidth": 2.0,
    "figure.dpi": 300
})

import glob
import sys

# Поиск всех ground_truth файлов
if len(sys.argv) > 1:
    target_dir = os.path.abspath(sys.argv[1])
else:
    target_dir = os.path.dirname(os.path.abspath(__file__))
    
csv_files = sorted(glob.glob(os.path.join(target_dir, "ground_truth_*.csv")))

if not csv_files:
    print(f"В папке {target_dir} не найдено файлов ground_truth_*.csv!")
    exit()

# Динамическая палитра для любого количества заездов
cmap = plt.get_cmap('tab10')
colors = [cmap(i % 10) for i in range(len(csv_files))]
labels = [f"Run {i+1}" for i in range(len(csv_files))]

dataframes = []
for file in csv_files:
    if os.path.exists(file):
        df = pd.read_csv(file)
        
        # Переименуем колонки для совместимости с кодом
        df = df.rename(columns={'X': 'X_m', 'Y': 'Y_m'})
        
        # Вычисляем дистанцию (Cumulative Euclidean distance)
        dx = df['X_m'].diff().fillna(0)
        dy = df['Y_m'].diff().fillna(0)
        dist_step = np.sqrt(dx**2 + dy**2)
        df['Distance_m'] = dist_step.cumsum()
        
        # Конвертируем mSv/h в uSv/h
        if 'DoseRate_mSv_h' in df.columns:
            df['Dose_Rate_uSv_h'] = df['DoseRate_mSv_h'] * 1000.0
            
        dataframes.append(df)
    else:
        print(f"Файл {file} не найден!")

if not dataframes:
    print("Нет данных для построения.")
    exit()

# ==========================================
# График 1: Траектория движения (X от Y)
# ==========================================
fig1, ax1 = plt.subplots(figsize=(8, 6))

for i, df in enumerate(dataframes):
    ax1.plot(df['X_m'], df['Y_m'], color=colors[i], label=labels[i], alpha=0.8)

ax1.set_xlabel('X Coordinate (m)')
ax1.set_ylabel('Y Coordinate (m)')
ax1.set_title('Spatial Trajectory of the Mobile Platform')
ax1.grid(True, linestyle='--', alpha=0.6)
ax1.legend(loc='best')
from matplotlib.ticker import MultipleLocator

ax1.set_xlim(0, 15)
ax1.set_ylim(0, 25)
ax1.xaxis.set_major_locator(MultipleLocator(5))
ax1.yaxis.set_major_locator(MultipleLocator(5))
ax1.set_aspect('equal')

fig1.tight_layout()
# Сохраняем в векторных форматах для Q1
fig1.savefig(os.path.join(target_dir, 'trajectory_Q1.pdf'), format='pdf', bbox_inches='tight')
fig1.savefig(os.path.join(target_dir, 'trajectory_Q1.svg'), format='svg', bbox_inches='tight')

# ==========================================
# График 2: Мощность дозы от дистанции
# ==========================================
fig2, ax2 = plt.subplots(figsize=(8, 6))

for i, df in enumerate(dataframes):
    # Используем сглаживание (опционально, если сырые данные слишком "шумные")
    # df['Dose_smooth'] = df['Dose_Rate_uSv_h'].rolling(window=3, min_periods=1).mean()
    
    ax2.plot(df['Distance_m'], df['Dose_Rate_uSv_h'], color=colors[i], label=labels[i], alpha=0.8)

ax2.set_xlabel('Traveled Distance (m)')
ax2.set_ylabel(r'Dose Rate ($\mu$Sv/h)') # Используем микрозиверты
ax2.set_title('Radiation Dose Rate vs. Distance')
ax2.grid(True, linestyle='--', alpha=0.6)
ax2.legend(loc='best')
ax2.set_ylim(0, 3.5e6) # Фиксированная шкала дозы до 3.0 * 10^6 мкЗв/ч
ax2.set_xlim(0, 25)    # Фиксированная шкала дистанции до 20 м

fig2.tight_layout()
# Сохраняем в векторных форматах для Q1
fig2.savefig(os.path.join(target_dir, 'dose_vs_distance_Q1.pdf'), format='pdf', bbox_inches='tight')
fig2.savefig(os.path.join(target_dir, 'dose_vs_distance_Q1.svg'), format='svg', bbox_inches='tight')

print("Векторные графики (PDF и SVG) успешно сгенерированы!")

# ==========================================
# Таблица: Сводные метрики
# ==========================================
print("\n" + "="*60)
print(f"{'Run':<10} | {'Length (m)':<12} | {'Time (s)':<10} | {'TID (uSv)':<15}")
print("-" * 60)

summary_data = []

for i, df in enumerate(dataframes):
    run_name = labels[i]
    # Вычисляем пройденную дистанцию
    length_m = df['Distance_m'].iloc[-1]
    
    # Вычисляем общее время
    if 'Time' in df.columns:
        time_s = df['Time'].iloc[-1] - df['Time'].iloc[0]
    else:
        time_s = 0.0
        
    # Вычисляем TID
    if 'Accumulated_TID_uSv' in df.columns:
        tid_usv = df['Accumulated_TID_uSv'].iloc[-1]
    else:
        tid_usv = 0.0
        
    print(f"{run_name:<10} | {length_m:<12.2f} | {time_s:<10.2f} | {tid_usv:<15.2f}")
    summary_data.append({
        'Run': run_name,
        'Length (m)': round(length_m, 2),
        'Time (s)': round(time_s, 2),
        'TID (uSv)': round(tid_usv, 2)
    })

print("="*60 + "\n")

# Сохраняем сводную таблицу в CSV
summary_df = pd.DataFrame(summary_data)
summary_path = os.path.join(target_dir, 'summary_metrics.csv')
summary_df.to_csv(summary_path, index=False)
print(f"Сводная таблица сохранена в '{summary_path}'")