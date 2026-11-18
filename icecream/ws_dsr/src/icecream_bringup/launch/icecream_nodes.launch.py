from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    args = [
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
    ]

    robot_id = LaunchConfiguration("robot_id")
    robot_model = LaunchConfiguration("robot_model")

    motion_manager_node = Node(
        package="icecream_motion_manager",
        executable="motion_manager",
        name="icecream_motion_manager",
        output="screen",
        additional_env={
            "ROBOT_ID": robot_id,
            "ROBOT_MODEL": robot_model,
        },
    )

    system_status_node = Node(
        package="icecream_system_status",
        executable="system_status",
        name="system_status_node",
        output="screen",
        additional_env={
            "ROBOT_ID": robot_id,
        },
    )

    return LaunchDescription(
        args + [
            motion_manager_node,
            system_status_node,
        ]
    )
