import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'smart_control'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Oleksandr Proskurin',
    maintainer_email='proskurin1408@gmail.com',
    description='Mission management, FSM, and tactical control',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mission_manager = smart_control.mission_manager:main',
            'mission_control = smart_control.mission_control:main',
            'waypoint_manager = smart_control.waypoint_manager:main',
            'payload_manager = smart_control.payload_manager:main',
            'safety_watchdog = smart_control.safety_watchdog:main',
            'nav_coordinator = smart_control.nav_coordinator:main',
            'telemetry_mux = smart_control.telemetry_mux:main',
        ],
    },
)