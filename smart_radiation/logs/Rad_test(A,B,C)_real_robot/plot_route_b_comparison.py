#!/usr/bin/env python3
"""
Скрипт генерації фінального публікаційного графіка для дисертації (Route B, реальний робот).

Вимоги:
  1. Один спільний векторний рисунок (SVG та PDF) високої якості (300 DPI, шрифти з зарубками).
  2. Апроксимація заїздів в одну лінію для Base NAV2 та одну лінію для Proposed.
  3. Суворий академічний стиль без зайвих іконок, маркерів чи заливок.
  4. Гладкі лінії потужності дози (гауссова фільтрація для усунення високочастотної телеметричної рябі).
  5. Підписи та назви українською мовою, вирівняні в одну горизонтальну лінію зверху.

Графік (а) зліва: Просторова траєкторія руху Y(X) з рівним масштабом осей (1:1).
Графік (б) справа: Профіль потужності дози від пройденої відстані.
"""

import os
import sys
import glob
import argparse
import pandas as pd
import numpy as np
from scipy.ndimage import gaussian_filter1d

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Академічні налаштування стилю для дисертації / наукових журналів (DSTU / IEEE / Elsevier)
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'DejaVu Serif'],
    'font.size': 13,
    'axes.labelsize': 14,
    'axes.titlesize': 15,
    'legend.fontsize': 12,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'lines.linewidth': 2.4,
    'figure.autolayout': False
})

def find_files(base_dir, route_letter='b'):
    alara_dir = os.path.join(base_dir, f'Route_{route_letter}_ALARA')
    base_dir_nav = os.path.join(base_dir, f'Route_{route_letter}_base_nav')

    alara_files = sorted(glob.glob(os.path.join(alara_dir, '*.csv')))
    base_files = sorted(glob.glob(os.path.join(base_dir_nav, '*.csv')))

    return base_files, alara_files

def average_trajectory(files, num_points=350):
    """Параметрична апроксимація траєкторії через нормовану довжину дуги u in [0, 1]."""
    all_x, all_y = [], []
    for f in files:
        df = pd.read_csv(f)
        dx = df['X_m'].diff().fillna(0)
        dy = df['Y_m'].diff().fillna(0)
        dist = np.sqrt(dx**2 + dy**2).cumsum()
        total_d = dist.iloc[-1]
        norm_d = dist / total_d
        u = np.linspace(0, 1, num_points)
        all_x.append(np.interp(u, norm_d, df['X_m']))
        all_y.append(np.interp(u, norm_d, df['Y_m']))
    return np.mean(all_x, axis=0), np.mean(all_y, axis=0)

def average_dose_profile(files, num_points=350, sigma=3.5):
    """Апроксимація профілю дози від відстані з гауссовим згладжуванням шуму."""
    dfs = [pd.read_csv(f) for f in files]
    max_d = float(np.mean([df['Distance_m'].iloc[-1] for df in dfs]))
    dist_grid = np.linspace(0, max_d, num_points)
    all_doses = [np.interp(dist_grid, df['Distance_m'], df['Dose_Rate_uSv_h']) for df in dfs]
    mean_dose = np.mean(all_doses, axis=0)
    smooth_dose = gaussian_filter1d(mean_dose, sigma=sigma)
    return dist_grid, smooth_dose

def calculate_summary_stats(files):
    lengths = []
    times = []
    tids = []
    speeds = []
    peaks = []

    for f in files:
        df = pd.read_csv(f)
        l = float(df['Distance_m'].iloc[-1])
        t = float(df['Time_sec'].iloc[-1] - df['Time_sec'].iloc[0])
        tid = float(df['Accum_Dose_uSv'].iloc[-1])
        peak = float(df['Dose_Rate_uSv_h'].max())
        lengths.append(l)
        times.append(t)
        tids.append(tid)
        speeds.append(l / t if t > 0 else 0.0)
        peaks.append(peak)

    return {
        'length_mean': float(np.mean(lengths)), 'length_std': float(np.std(lengths)),
        'time_mean': float(np.mean(times)), 'time_std': float(np.std(times)),
        'tid_mean': float(np.mean(tids)), 'tid_std': float(np.std(tids)),
        'speed_mean': float(np.mean(speeds)), 'speed_std': float(np.std(speeds)),
        'peak_mean': float(np.mean(peaks))
    }

def main():
    parser = argparse.ArgumentParser(description="Побудова фінального графіка порівняння Base NAV2 та Proposed для дисертації")
    parser.add_argument('--route', type=str, default='b', help='Літера маршруту: a, b або c (за замовчуванням b)')
    parser.add_argument('--unit', choices=['mSv', 'uSv'], default='mSv', help='Одиниця дози (mSv або uSv, за замовчуванням mSv)')
    parser.add_argument('--out-name', type=str, default=None, help='Базове ім’я вихідного файлу (без розширення)')
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    route_letter = args.route.lower()
    base_files, alara_files = find_files(current_dir, route_letter)

    if not base_files or not alara_files:
        print(f"Помилка: Не знайдено файлів у {current_dir}/Route_{route_letter}_base_nav або Route_{route_letter}_ALARA")
        sys.exit(1)

    # Статистичний розрахунок
    stats_base = calculate_summary_stats(base_files)
    stats_prop = calculate_summary_stats(alara_files)
    tid_reduction = ((stats_base['tid_mean'] - stats_prop['tid_mean']) / stats_base['tid_mean']) * 100.0

    print("\n" + "="*76)
    print(f" УЗАГАЛЬНЕНІ РЕЗУЛЬТАТИ ЕКСПЕРИМЕНТУ (Route {route_letter.upper()}, 5 заїздів кожної конфігурації)")
    print("="*76)
    print(f"{'Параметр':<28} | {'Base NAV2':<18} | {'Proposed':<18} | {'Ефект':<12}")
    print("-" * 76)
    print(f"{'Довжина шляху L, м':<28} | {stats_base['length_mean']:.2f} ± {stats_base['length_std']:.2f}     | {stats_prop['length_mean']:.2f} ± {stats_prop['length_std']:.2f}     | {stats_prop['length_mean'] - stats_base['length_mean']:+.2f} м")
    print(f"{'Час руху T, с':<28} | {stats_base['time_mean']:.1f} ± {stats_base['time_std']:.1f}       | {stats_prop['time_mean']:.1f} ± {stats_prop['time_std']:.1f}       | {stats_prop['time_mean'] - stats_base['time_mean']:+.1f} с")
    print(f"{'Середня швидкість V, м/с':<28} | {stats_base['speed_mean']:.2f} ± {stats_base['speed_std']:.2f}     | {stats_prop['speed_mean']:.2f} ± {stats_prop['speed_std']:.2f}     | {stats_prop['speed_mean'] - stats_base['speed_mean']:+.2f} м/с")
    print(f"{'Інтегральна доза TID, мкЗв':<28} | {stats_base['tid_mean']:.2f} ± {stats_base['tid_std']:.2f}   | {stats_prop['tid_mean']:.2f} ± {stats_prop['tid_std']:.2f}   | -{tid_reduction:.1f}%")
    print("="*76 + "\n")

    # Апроксимація траєкторій та доз
    mx_base, my_base = average_trajectory(base_files)
    mx_prop, my_prop = average_trajectory(alara_files)

    d_grid_base, dose_base_raw = average_dose_profile(base_files, sigma=3.5)
    d_grid_prop, dose_prop_raw = average_dose_profile(alara_files, sigma=3.5)

    scale = 1.0 / 1000.0 if args.unit == 'mSv' else 1.0
    dose_unit_str = "мЗв/год" if args.unit == 'mSv' else "мкЗв/год"
    dose_base = dose_base_raw * scale
    dose_prop = dose_prop_raw * scale

    # Кольорова палітра для публікації
    c_base = '#d62728'   # Червона штрихова лінія (Base NAV2)
    c_prop = '#1f77b4'   # Синя суцільна лінія (Proposed)

    # Створення полотна з точним співвідношенням сторін (width_ratios)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.5, 4.8), gridspec_kw={'width_ratios': [1.4, 1.0]})
    fig.subplots_adjust(wspace=0.22, top=0.88, bottom=0.15, left=0.07, right=0.97)

    # -------------------------------------------------------------
    # (а) Лівий графік: Просторова траєкторія руху Y(X)
    # -------------------------------------------------------------
    ax1.plot(mx_base, my_base, color=c_base, linestyle='--', label='Base NAV2')
    ax1.plot(mx_prop, my_prop, color=c_prop, linestyle='-', label='Proposed')

    ax1.set_xlabel('Координата X, м')
    ax1.set_ylabel('Координата Y, м')
    ax1.set_xlim(-0.8, 11.8)
    ax1.set_ylim(-4.5, 1.0)
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.set_aspect('equal', adjustable='box')
    ax1.legend(loc='lower right', framealpha=0.92)

    # -------------------------------------------------------------
    # (б) Правий графік: Потужність дози від пройденої відстані
    # -------------------------------------------------------------
    ax2.plot(d_grid_base, dose_base, color=c_base, linestyle='--', label='Base NAV2')
    ax2.plot(d_grid_prop, dose_prop, color=c_prop, linestyle='-', label='Proposed')

    ax2.set_xlabel('Пройдена відстань, м')
    ax2.set_ylabel(f'Потужність дози, {dose_unit_str}')
    ax2.set_xlim(0, max(d_grid_base.max(), d_grid_prop.max()) + 0.6)
    ax2.set_ylim(0, 16.5 if args.unit == 'mSv' else 16500)
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend(loc='upper right', framealpha=0.92)

    # Назви підграфіків суворо на одній горизонтальній лінії (y=1.0)
    ax1.set_title('(а) Просторова траєкторія руху Y(X)', pad=12, fontweight='bold', y=1.0)
    ax2.set_title('(б) Потужність дози від пройденої відстані', pad=12, fontweight='bold', y=1.0)

    # -------------------------------------------------------------
    # Збереження у векторні формати
    # -------------------------------------------------------------
    base_name = args.out_name or f"Route_{route_letter.upper()}_comparison"
    out_pdf = os.path.join(current_dir, f"{base_name}.pdf")
    out_svg = os.path.join(current_dir, f"{base_name}.svg")

    fig.savefig(out_pdf, format='pdf', bbox_inches='tight', dpi=300)
    fig.savefig(out_svg, format='svg', bbox_inches='tight', dpi=300)
    plt.close(fig)

    print(f"Графік успішно збережено:")
    print(f"  PDF: {out_pdf}")
    print(f"  SVG: {out_svg}\n")

if __name__ == '__main__':
    main()
