import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'smart_server'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'meshes'), glob('meshes/*.STL')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Oleksandr Proskurin',
    maintainer_email='proskurin1408@gmail.com',
    description='Digital Twin Server infrastructure',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'heartbeat_pub = smart_server.heartbeat_pub:main',
            'sdf_visualizer = smart_server.sdf_visualizer_node:main',
            'twin_orchestrator = smart_server.twin_orchestrator:main',
            'shadow_teleop_sim = smart_server.shadow_teleop_sim:main',
            'shadow_teleop_real = smart_server.shadow_teleop_real:main',
            'map_to_image = smart_server.map_to_image:main',
            'web_server = smart_server.web_server:main',
        ],
    },
)
