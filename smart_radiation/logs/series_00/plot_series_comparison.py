#!/usr/bin/env python3
"""
Скрипт генерації публікаційних порівняльних графіків для серії експериментів (series_00).
Підтримує побудову для маршрутів R1, R2 та R3:
  - Baseline: {route}_baseline_01, 02, 03
  - Proposed: {route}_proposed_01, 02, 03

Вимоги:
  1. Один векторний рисунок (SVG та PDF, 300 DPI, шрифти з зарубками для дисертації).
  2. Апроксимація заїздів в 1 лінію для Baseline та 1 лінію для Proposed.
  3. Підписи в легенді: Baseline та Proposed.
  4. Без додаткових маркерів старту/фінішу та кольорових заливок.
  5. Гладкі лінії профілю дози (гауссова фільтрація шуму).
  6. Підписи осей та заголовки українською мовою, вирівняні в одну лінію зверху.

Графік (а) зліва: Просторова траєкторія руху Y(X) з рівним масштабом (1:1).
Графік (б) справа: Потужність дози від пройденої відстані.
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

# Налаштування стилю для дисертаційного видання (Times New Roman / DejaVu Serif)
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

def find_run_dirs(base_dir, route_name="R3"):
    base_pattern = os.path.join(base_dir, f"{route_name}_baseline_*")
    prop_pattern = os.path.join(base_dir, f"{route_name}_proposed_*")

    base_dirs = sorted([d for d in glob.glob(base_pattern) if os.path.isdir(d)])
    prop_dirs = sorted([d for d in glob.glob(prop_pattern) if os.path.isdir(d)])

    return base_dirs, prop_dirs

def average_trajectory(run_dirs, num_points=350):
    all_x, all_y = [], []
    for d in run_dirs:
        csv_file = os.path.join(d, 'samples.csv')
        df = pd.read_csv(csv_file)
        dx = df['x_map_m'].diff().fillna(0)
        dy = df['y_map_m'].diff().fillna(0)
        dist = np.sqrt(dx**2 + dy**2).cumsum()
        total_d = dist.iloc[-1]
        norm_d = dist / total_d
        u = np.linspace(0, 1, num_points)
        all_x.append(np.interp(u, norm_d, df['x_map_m']))
        all_y.append(np.interp(u, norm_d, df['y_map_m']))
    return np.mean(all_x, axis=0), np.mean(all_y, axis=0)

def average_dose_profile(run_dirs, num_points=350, sigma=3.5):
    dfs = [pd.read_csv(os.path.join(d, 'samples.csv')) for d in run_dirs]
    max_d = float(np.mean([df['path_valid_m'].iloc[-1] for df in dfs]))
    dist_grid = np.linspace(0, max_d, num_points)
    all_doses = []
    for df in dfs:
        all_doses.append(np.interp(dist_grid, df['path_valid_m'], df['dose_rate_uSv_h']))
    mean_dose = np.mean(all_doses, axis=0)
    smooth_dose = gaussian_filter1d(mean_dose, sigma=sigma)
    return dist_grid, smooth_dose

def calculate_summary_stats(run_dirs):
    lengths = []
    times = []
    tids = []
    speeds = []
    peaks = []

    for d in run_dirs:
        csv_file = os.path.join(d, 'samples.csv')
        df = pd.read_csv(csv_file)
        l = float(df['path_valid_m'].iloc[-1])
        t = float(df['t_elapsed_s'].iloc[-1] - df['t_elapsed_s'].iloc[0])
        tid = float(df['exposure_valid_uSv'].iloc[-1])
        peak = float(df['dose_rate_uSv_h'].max())
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

def process_route(current_dir, route_name, unit='mSv', out_name=None):
    route_name = route_name.upper()
    base_dirs, prop_dirs = find_run_dirs(current_dir, route_name)

    if not base_dirs or not prop_dirs:
        print(f"Помилка: Не знайдено директорій {route_name}_baseline_* або {route_name}_proposed_* у {current_dir}")
        return False

    print(f"\nОбробка маршруту {route_name}:")
    print(f"  Baseline папки ({len(base_dirs)}): {[os.path.basename(d) for d in base_dirs]}")
    print(f"  Proposed папки ({len(prop_dirs)}): {[os.path.basename(d) for d in prop_dirs]}")

    # Статистика
    stats_base = calculate_summary_stats(base_dirs)
    stats_prop = calculate_summary_stats(prop_dirs)
    tid_reduction = ((stats_base['tid_mean'] - stats_prop['tid_mean']) / stats_base['tid_mean']) * 100.0
    peak_reduction = ((stats_base['peak_mean'] - stats_prop['peak_mean']) / stats_base['peak_mean']) * 100.0

    print("="*76)
    print(f" УЗАГАЛЬНЕНІ РЕЗУЛЬТАТИ ЕКСПЕРИМЕНТУ ({route_name}, по 3 заїзди кожної конфігурації)")
    print("="*76)
    print(f"{'Параметр':<28} | {'Baseline':<18} | {'Proposed':<18} | {'Ефект':<12}")
    print("-" * 76)
    print(f"{'Довжина шляху L, м':<28} | {stats_base['length_mean']:.2f} ± {stats_base['length_std']:.2f}     | {stats_prop['length_mean']:.2f} ± {stats_prop['length_std']:.2f}     | {stats_prop['length_mean'] - stats_base['length_mean']:+.2f} м")
    print(f"{'Час руху T, с':<28} | {stats_base['time_mean']:.1f} ± {stats_base['time_std']:.1f}       | {stats_prop['time_mean']:.1f} ± {stats_prop['time_std']:.1f}       | {stats_prop['time_mean'] - stats_base['time_mean']:+.1f} с")
    print(f"{'Середня швидкість V, м/с':<28} | {stats_base['speed_mean']:.2f} ± {stats_base['speed_std']:.2f}     | {stats_prop['speed_mean']:.2f} ± {stats_prop['speed_std']:.2f}     | {stats_prop['speed_mean'] - stats_base['speed_mean']:+.2f} м/с")
    print(f"{'Інтегральна доза TID, мкЗв':<28} | {stats_base['tid_mean']:.1f} ± {stats_base['tid_std']:.1f}   | {stats_prop['tid_mean']:.1f} ± {stats_prop['tid_std']:.1f}   | -{tid_reduction:.1f}%")
    print(f"{'Пікова потужність, мкЗв/год':<28} | {stats_base['peak_mean']:<18.0f} | {stats_prop['peak_mean']:<18.0f} | -{peak_reduction:.1f}%")
    print("="*76)

    # Усереднення
    mx_base, my_base = average_trajectory(base_dirs)
    mx_prop, my_prop = average_trajectory(prop_dirs)

    d_grid_base, dose_base_raw = average_dose_profile(base_dirs, sigma=3.5)
    d_grid_prop, dose_prop_raw = average_dose_profile(prop_dirs, sigma=3.5)

    scale = 1.0 / 1000.0 if unit == 'mSv' else 1.0
    dose_unit_str = "мЗв/год" if unit == 'mSv' else "мкЗв/год"
    dose_base = dose_base_raw * scale
    dose_prop = dose_prop_raw * scale

    # Кольори для дисертації
    c_base = '#d62728'   # Червоний пунктир
    c_prop = '#1f77b4'   # Синій суцільний

    # Адаптивний розрахунок меж з мінімальним розмахом X >= 8.0м для красивого вигляду та читабельності легенди
    all_x = np.concatenate([mx_base, mx_prop])
    all_y = np.concatenate([my_base, my_prop])
    
    x_center = (all_x.min() + all_x.max()) / 2.0
    span_x = max(8.0, (all_x.max() - all_x.min()) + 2.0)
    x_min = np.floor(x_center - span_x / 2.0)
    x_max = np.ceil(x_center + span_x / 2.0)
    
    y_min = np.floor(all_y.min() - 1.2)
    y_max = np.ceil(all_y.max() + 1.2)

    dx = x_max - x_min
    dy = y_max - y_min
    aspect_ratio_data = dx / dy

    # Ширина колонки ax1 розраховується з урахуванням висоти H=6.0 та aspect='equal'
    ax1_w_ratio = max(1.0, min(1.6, aspect_ratio_data * 2.8))
    ax2_w_ratio = 1.8

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 6.0), gridspec_kw={'width_ratios': [ax1_w_ratio, ax2_w_ratio]})
    fig.subplots_adjust(wspace=0.25, top=0.90, bottom=0.12, left=0.08, right=0.96)

    # -------------------------------------------------------------
    # (а) Лівий графік: Просторова траєкторія руху Y(X)
    # -------------------------------------------------------------
    ax1.plot(mx_base, my_base, color=c_base, linestyle='--', label='Baseline')
    ax1.plot(mx_prop, my_prop, color=c_prop, linestyle='-', label='Proposed')

    ax1.set_xlabel('Координата X, м')
    ax1.set_ylabel('Координата Y, м')
    ax1.set_xlim(x_min, x_max)
    ax1.set_ylim(y_min, y_max)
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.set_aspect('equal', adjustable='box')
    ax1.legend(loc='lower right', framealpha=0.92)

    # -------------------------------------------------------------
    # (б) Правий графік: Потужність дози від пройденої відстані
    # -------------------------------------------------------------
    ax2.plot(d_grid_base, dose_base, color=c_base, linestyle='--', label='Baseline')
    ax2.plot(d_grid_prop, dose_prop, color=c_prop, linestyle='-', label='Proposed')

    ax2.set_xlabel('Пройдена відстань, м')
    ax2.set_ylabel(f'Потужність дози, {dose_unit_str}')
    ax2.set_xlim(0, max(d_grid_base.max(), d_grid_prop.max()) + 1.0)
    ax2.set_ylim(0, max(dose_base.max(), dose_prop.max()) * 1.15)
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend(loc='upper right', framealpha=0.92)

    # Заголовки суворо на одній горизонтальній лінії
    ax1.set_title('(а) Просторова траєкторія руху Y(X)', pad=12, fontweight='bold', y=1.0)
    ax2.set_title('(б) Потужність дози від пройденої відстані', pad=12, fontweight='bold', y=1.0)

    # Збереження у SVG та PDF
    base_name = out_name or f"{route_name}_comparison"
    out_pdf = os.path.join(current_dir, f"{base_name}.pdf")
    out_svg = os.path.join(current_dir, f"{base_name}.svg")

    fig.savefig(out_pdf, format='pdf', bbox_inches='tight', dpi=300)
    fig.savefig(out_svg, format='svg', bbox_inches='tight', dpi=300)
    plt.close(fig)

    print(f"Графік {route_name} успішно збережено:")
    print(f"  PDF: {out_pdf}")
    print(f"  SVG: {out_svg}\n")
    return True

def main():
    parser = argparse.ArgumentParser(description="Побудова графіків порівняння Baseline та Proposed для series_00")
    parser.add_argument('-r', '--route', type=str, default='all', help='Назва маршруту: R1, R2, R3 або all (за замовчуванням all)')
    parser.add_argument('--unit', choices=['mSv', 'uSv'], default='mSv', help='Одиниця дози (mSv або uSv, за замовчуванням mSv)')
    parser.add_argument('--out-name', type=str, default=None, help='Базове ім’я вихідного файлу')
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))

    if args.route.lower() == 'all':
        for r in ['R1', 'R2', 'R3']:
            process_route(current_dir, r, unit=args.unit)
    else:
        process_route(current_dir, args.route.upper(), unit=args.unit, out_name=args.out_name)

if __name__ == '__main__':
    main()
