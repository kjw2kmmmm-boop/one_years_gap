import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression


def generate_launch_description():
    args = [
        DeclareLaunchArgument(
            "mode",
            default_value="virtual",
            description="Robot operation mode: virtual | real",
        ),
        DeclareLaunchArgument(
            "host",
            default_value="127.0.0.1",
            description="Robot IP (127.0.0.1 for virtual, 192.168.1.100 for real)",
        ),
        DeclareLaunchArgument(
            "port",
            default_value="12345",
            description="Robot port",
        ),
        DeclareLaunchArgument(
            "robot_id",
            default_value="dsr01",
            description="Doosan robot namespace / ID",
        ),
        DeclareLaunchArgument(
            "robot_model",
            default_value="m0609",
            description="Doosan robot model",
        ),
        DeclareLaunchArgument(
            "camera",
            default_value="false",
            description="Include RealSense camera bringup (true | false)",
        ),
        DeclareLaunchArgument(
            "with_robot",
            default_value="true",
            description="Also launch m0609_rg2_bringup (true | false)",
        ),
    ]

    m0609_launch_dir = os.path.join(
        get_package_share_directory("m0609_rg2_bringup"), "launch"
    )
    icecream_launch_dir = os.path.join(
        get_package_share_directory("icecream_bringup"), "launch"
    )

    with_robot_no_camera = PythonExpression(
        [
            "'",
            LaunchConfiguration("with_robot"),
            "' == 'true' and '",
            LaunchConfiguration("camera"),
            "' != 'true'",
        ]
    )
    with_robot_camera = PythonExpression(
        [
            "'",
            LaunchConfiguration("with_robot"),
            "' == 'true' and '",
            LaunchConfiguration("camera"),
            "' == 'true'",
        ]
    )

    robot_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(m0609_launch_dir, "bringup.launch.py")
        ),
        launch_arguments={
            "mode": LaunchConfiguration("mode"),
            "host": LaunchConfiguration("host"),
            "port": LaunchConfiguration("port"),
        }.items(),
        condition=IfCondition(with_robot_no_camera),
    )

    robot_camera_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(m0609_launch_dir, "bringup_camera.launch.py")
        ),
        launch_arguments={
            "mode": LaunchConfiguration("mode"),
            "host": LaunchConfiguration("host"),
            "port": LaunchConfiguration("port"),
        }.items(),
        condition=IfCondition(with_robot_camera),
    )

    icecream_nodes = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(icecream_launch_dir, "icecream_nodes.launch.py")
        ),
        launch_arguments={
            "robot_id": LaunchConfiguration("robot_id"),
            "robot_model": LaunchConfiguration("robot_model"),
        }.items(),
    )

    return LaunchDescription(
        args + [
            robot_bringup,
            robot_camera_bringup,
            icecream_nodes,
        ]
    )
