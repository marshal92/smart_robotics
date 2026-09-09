#!/usr/bin/env python3
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Отключаем оконный интерфейс для стабильного рендера
import matplotlib.pyplot as plt
import os

# Настройки графиков для научных журналов Q1
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 14,
    'axes.labelsize': 14,
    'axes.titlesize': 16,
    'legend.fontsize': 12,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'lines.linewidth': 2.0,
    'figure.autolayout': False
})

# === СПИСКИ ФАЙЛОВ ===
# Пропиши полные пути или убедись, что файлы лежат рядом со скриптом
baseline_files = [
    "baseline_1.csv", "baseline_2.csv", "baseline_3.csv", "baseline_4.csv", "baseline_5.csv"
]
alara_files = [
    "alara_1.csv", "alara_2.csv", "alara_3.csv", "alara_4.csv", "alara_5.csv"
]

colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
labels = ['Run 1', 'Run 2', 'Run 3', 'Run 4', 'Run 5']

def load_data(file_list):
    dataframes = []
    for file in file_list:
        if os.path.exists(file):
            dataframes.append(pd.read_csv(file))
        else:
            print(f"Предупреждение: Файл {file} не найден!")
    return dataframes

print("Загрузка логов Baseline...")
baseline_dfs = load_data(baseline_files)

print("Загрузка логов ALARA...")
alara_dfs = load_data(alara_files)

if not baseline_dfs or not alara_dfs:
    print("Ошибка: Для построения графиков нужны данные ОБЕИХ конфигураций.")
    exit()

# =========================================================
# РИСУНОК 6: Пространственные траектории (X vs Y)
# =========================================================
fig1, (ax1_traj, ax2_traj) = plt.subplots(1, 2, figsize=(18, 7), sharey=True, sharex=True)
fig1.subplots_adjust(wspace=0.05)

for i, df in enumerate(baseline_dfs):
    ax1_traj.plot(df['X_m'], df['Y_m'], color=colors[i], label=labels[i], alpha=0.8)

ax1_traj.set_title("Baseline Nav2", pad=15)
ax1_traj.set_xlabel("X Coordinate (m)")
ax1_traj.set_ylabel("Y Coordinate (m)")
ax1_traj.grid(True, linestyle='--', alpha=0.6)
ax1_traj.legend(loc='best', framealpha=0.9)
ax1_traj.set_aspect('equal', adjustable='box') # Сохраняем физические пропорции пространства

for i, df in enumerate(alara_dfs):
    ax2_traj.plot(df['X_m'], df['Y_m'], color=colors[i], label=labels[i], alpha=0.8)

ax2_traj.set_title("ALARA Navigation", pad=15)
ax2_traj.set_xlabel("X Coordinate (m)")
ax2_traj.grid(True, linestyle='--', alpha=0.6)
ax2_traj.legend(loc='best', framealpha=0.9)
ax2_traj.set_aspect('equal', adjustable='box')

fig1.savefig('Fig_6_Trajectories_Unified.pdf', format='pdf', bbox_inches='tight', dpi=300)
fig1.savefig('Fig_6_Trajectories_Unified.svg', format='svg', bbox_inches='tight', dpi=300)
print("Успех: Fig_6_Trajectories_Unified (PDF/SVG) сохранен.")


# =========================================================
# РИСУНОК 7: Мощность дозы от дистанции
# =========================================================
fig2, (ax1_dose, ax2_dose) = plt.subplots(1, 2, figsize=(18, 7), sharey=True)
fig2.subplots_adjust(wspace=0.05) 

for i, df in enumerate(baseline_dfs):
    ax1_dose.plot(df['Distance_m'], df['Dose_Rate_uSv_h'] / 1000.0, color=colors[i], label=labels[i], alpha=0.8)

ax1_dose.set_title("Baseline Nav2", pad=15)
ax1_dose.set_xlabel("Traveled Distance (m)")
ax1_dose.set_ylabel("Dose Rate (mSv/h)")
ax1_dose.set_xlim(0, 14) # Жесткий лимит 14 метров
ax1_dose.grid(True, linestyle='--', alpha=0.4)
ax1_dose.legend(loc='upper right', framealpha=0.9)

for i, df in enumerate(alara_dfs):
    ax2_dose.plot(df['Distance_m'], df['Dose_Rate_uSv_h'] / 1000.0, color=colors[i], label=labels[i], alpha=0.8)

ax2_dose.set_title("ALARA Navigation", pad=15)
ax2_dose.set_xlabel("Traveled Distance (m)")
ax2_dose.set_xlim(0, 14) # Тот же жесткий лимит 14 метров
ax2_dose.grid(True, linestyle='--', alpha=0.4)
ax2_dose.legend(loc='upper right', framealpha=0.9)

fig2.savefig('Fig_7_Profiles_Unified.pdf', format='pdf', bbox_inches='tight', dpi=300)
fig2.savefig('Fig_7_Profiles_Unified.svg', format='svg', bbox_inches='tight', dpi=300)
print("Успех: Fig_7_Profiles_Unified (PDF/SVG) сохранен.")