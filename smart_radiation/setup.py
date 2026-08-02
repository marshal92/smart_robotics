import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'smart_radiation'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'maps'), glob('maps/*.npy')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='oleksandr',
    maintainer_email='proskurin1408@gmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'radiation_field_server = smart_radiation.radiation_field_server:main',
            'virtual_geiger = smart_radiation.virtual_geiger:main',
            'dose_logger = smart_radiation.dose_logger:main',
            'generate_map = smart_radiation.generate_map:main',
            'view_map = smart_radiation.view_map:main',
        ],
    },
)
