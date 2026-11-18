from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'icecream_motion_manager'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ubuntu',
    maintainer_email='ubuntu@todo.todo',
    description='Motion manager ROS2 service server for the icecream cobot system',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'motion_manager = icecream_motion_manager.motion_manager_node:main',
            'move_home = icecream_motion_manager.move_home:main',
            'move_to_scoop = icecream_motion_manager.move_to_scoop:main',
            'move_cup_z = icecream_motion_manager.move_cup_z:main',
            'move_to_plate = icecream_motion_manager.move_to_plate:main',
            'move_to_flavor = icecream_motion_manager.move_to_flavor:main',
            'grip_and_lift = icecream_motion_manager.grip_and_lift:main',
            'griper_release = icecream_motion_manager.gripper:main_release',
            'griper_grap = icecream_motion_manager.gripper:main_grap',
            'calibrate_cup_z = icecream_motion_manager.calibrate_cup_z:main',
        ],
    },
)
