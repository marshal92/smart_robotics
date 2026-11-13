import cv2
import numpy as np
import yaml

# 1. Specify file paths
map_image_path = 'shelter_zero_empty_1.pgm' # or .png if converted
map_yaml_path = 'shelter_zero_empty_1.yaml'

# 2. Extract map resolution from YAML file
try:
    with open(map_yaml_path, 'r') as file:
        map_info = yaml.safe_load(file)
        resolution = map_info['resolution']
except FileNotFoundError:
    print("YAML file not found. Using default resolution 0.05")
    resolution = 0.05

# 3. Load grayscale map image
img = cv2.imread(map_image_path, cv2.IMREAD_GRAYSCALE)

if img is None:
    print(f"Error: failed to load image {map_image_path}")
    exit()

# 4. Count free pixels.
# In ROS maps, free space is 254. Use 250-255 range to absorb minor compression artifacts.
free_pixels = np.sum(img >= 250)

# 5. Compute area
pixel_area = resolution * resolution
total_area = free_pixels * pixel_area

print("=== AREA CALCULATION RESULTS ===")
print(f"Map resolution: {resolution} m/pixel")
print(f"Single pixel area: {pixel_area:.6f} sq.m")
print(f"Free pixels found: {free_pixels}")
print(f"Total room area: {total_area:.3f} sq.m")