import cv2
import numpy as np
import yaml

# 1. Задаем пути к файлам
map_image_path = 'shelter_zero_empty_1.pgm' # или .png, если конвертировал
map_yaml_path = 'shelter_zero_empty_1.yaml'

# 2. Достаем разрешение (resolution) из yaml файла
try:
    with open(map_yaml_path, 'r') as file:
        map_info = yaml.safe_load(file)
        resolution = map_info['resolution']
except FileNotFoundError:
    print(f"YAML файл не найден. Использую стандартное разрешение 0.05")
    resolution = 0.05

# 3. Загружаем картинку в градациях серого
img = cv2.imread(map_image_path, cv2.IMREAD_GRAYSCALE)

if img is None:
    print(f"Ошибка: не удалось загрузить изображение {map_image_path}")
    exit()

# 4. Считаем свободные пиксели. 
# В ROS белый цвет - это 254. Берем диапазон 250-255 на случай мелких артефактов сжатия.
free_pixels = np.sum(img >= 250)

# 5. Математика
pixel_area = resolution * resolution
total_area = free_pixels * pixel_area

print("=== РЕЗУЛЬТАТЫ ПОДСЧЕТА ===")
print(f"Разрешение карты: {resolution} м/пиксель")
print(f"Площадь одного пикселя: {pixel_area:.6f} кв.м")
print(f"Найдено свободных пикселей: {free_pixels}")
print(f"Итоговая площадь комнаты: {total_area:.3f} квадратных метров")