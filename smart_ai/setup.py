import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'smart_ai'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools', 'ultralytics', 'faster-whisper', 'pyaudio', 'opencv-python'],
    zip_safe=True,
    maintainer='Oleksandr Proskurin',
    description='AI Vision and Voice commands',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'smart_ears = smart_ai.smart_ears:main',
            'yolo_publisher = smart_ai.yolo_publisher:main',
        ],
    },
)