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

# Список твоих CSV файлов
csv_files = [
    "mission_20260514_132032.csv",
    "mission_20260514_132411.csv",
    "mission_20260514_132554.csv",
    "mission_20260514_132730.csv",
    "mission_20260514_132902.csv"
]

# Цветовая палитра для различения заездов (научный стиль)
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
labels = ['Run 1', 'Run 2', 'Run 3', 'Run 4', 'Run 5']

dataframes = []
for file in csv_files:
    if os.path.exists(file):
        dataframes.append(pd.read_csv(file))
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
ax1.axis('equal') # Сохраняет реальные пропорции пространства

fig1.tight_layout()
# Сохраняем в векторных форматах для Q1
fig1.savefig('trajectory_Q1.pdf', format='pdf', bbox_inches='tight')
fig1.savefig('trajectory_Q1.svg', format='svg', bbox_inches='tight')

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

fig2.tight_layout()
# Сохраняем в векторных форматах для Q1
fig2.savefig('dose_vs_distance_Q1.pdf', format='pdf', bbox_inches='tight')
fig2.savefig('dose_vs_distance_Q1.svg', format='svg', bbox_inches='tight')

print("Векторные графики (PDF и SVG) успешно сгенерированы!")