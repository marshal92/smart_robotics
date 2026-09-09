#!/usr/bin/env python3
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Отключаем оконный интерфейс
import matplotlib.pyplot as plt
import os

# Настройки графиков для научных журналов Q1
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 14,
    'axes.labelsize': 14,
    'axes.titlesize': 16,
    'legend.fontsize': 11,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'lines.linewidth': 2.0,
    'figure.autolayout': False
})

# === СПИСКИ ФАЙЛОВ ===
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

print("Загрузка логов...")
baseline_dfs = load_data(baseline_files)
alara_dfs = load_data(alara_files)

if not baseline_dfs or not alara_dfs:
    print("Ошибка: Для построения графика нужны данные ОБЕИХ конфигураций.")
    exit()

# === СОЗДАНИЕ МЕГА-ХОЛСТА ===
fig, axes = plt.subplots(2, 2, figsize=(18, 12), gridspec_kw={'height_ratios': [1.4, 1]})

# hspace уменьшен до 0.08 для устранения дыры между верхними и нижними графиками
fig.subplots_adjust(wspace=0.08, hspace=0.2) 

ax_t_base = axes[0, 0]
ax_t_alara = axes[0, 1]
ax_d_base = axes[1, 0]
ax_d_alara = axes[1, 1]

ax_t_alara.sharey(ax_t_base)
ax_t_alara.sharex(ax_t_base)
ax_d_alara.sharey(ax_d_base)

# ---------------------------------------------------------
# ВЕРХНИЙ РЯД: Траектории (a, b)
# ---------------------------------------------------------
for i, df in enumerate(baseline_dfs):
    ax_t_base.plot(df['X_m'], df['Y_m'], color=colors[i], label=labels[i], alpha=0.8)

ax_t_base.set_title("(a) Baseline Nav2: Spatial Trajectory", pad=15)
ax_t_base.set_xlabel("X Coordinate (m)")
ax_t_base.set_ylabel("Y Coordinate (m)")
ax_t_base.grid(True, linestyle='--', alpha=0.4)
ax_t_base.legend(loc='lower right', framealpha=0.9) # Жесткая фиксация в нижнем правом углу
ax_t_base.set_aspect('equal', adjustable='box') 

for i, df in enumerate(alara_dfs):
    ax_t_alara.plot(df['X_m'], df['Y_m'], color=colors[i], label=labels[i], alpha=0.8)

ax_t_alara.set_title("(b) ALARA Navigation: Spatial Trajectory", pad=15)
ax_t_alara.set_xlabel("X Coordinate (m)")
ax_t_alara.grid(True, linestyle='--', alpha=0.4)
ax_t_alara.legend(loc='lower right', framealpha=0.9) # Жесткая фиксация в нижнем правом углу
ax_t_alara.set_aspect('equal', adjustable='box')
plt.setp(ax_t_alara.get_yticklabels(), visible=False) 

# ---------------------------------------------------------
# НИЖНИЙ РЯД: Профили дозы (c, d)
# ---------------------------------------------------------
# Окно сглаживания телеметрии. Если графики останутся резкими, можно увеличить window до 15 или 20.
SMOOTHING_WINDOW = 5

for i, df in enumerate(baseline_dfs):
    # Сглаживание сырых данных скользящим средним
    smooth_dose = df['Dose_Rate_uSv_h'].rolling(window=SMOOTHING_WINDOW, min_periods=1).mean()
    ax_d_base.plot(df['Distance_m'], smooth_dose / 1000.0, color=colors[i], label=labels[i], alpha=0.8)

ax_d_base.set_title("(c) Baseline Nav2: Dose Rate Profile", pad=15)
ax_d_base.set_xlabel("Traveled Distance (m)")
ax_d_base.set_ylabel("Dose Rate (mSv/h)")
ax_d_base.set_xlim(0, 8) 
ax_d_base.grid(True, linestyle='--', alpha=0.4)
ax_d_base.legend(loc='upper right', framealpha=0.9) 

for i, df in enumerate(alara_dfs):
    # Сглаживание сырых данных скользящим средним
    smooth_dose = df['Dose_Rate_uSv_h'].rolling(window=SMOOTHING_WINDOW, min_periods=1).mean()
    ax_d_alara.plot(df['Distance_m'], smooth_dose / 1000.0, color=colors[i], label=labels[i], alpha=0.8)

ax_d_alara.set_title("(d) ALARA Navigation: Dose Rate Profile", pad=15)
ax_d_alara.set_xlabel("Traveled Distance (m)")
ax_d_alara.set_xlim(0, 8) 
ax_d_alara.grid(True, linestyle='--', alpha=0.4)
ax_d_alara.legend(loc='upper right', framealpha=0.9) 
plt.setp(ax_d_alara.get_yticklabels(), visible=False) 

# === СОХРАНЕНИЕ ===
plt.savefig('Fig_6_Combined_Navigation.pdf', format='pdf', bbox_inches='tight', dpi=300)
print("Успех: Финальная композиция со сглаживанием телеметрии сохранена!")