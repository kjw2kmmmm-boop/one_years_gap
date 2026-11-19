from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    args = [
        DeclareLaunchArgument(
            "node_name",
            default_value="icecream_order_manager",
            description="ROS2 node name for order_manager",
        ),
    ]

    order_manager_node = Node(
        package="icecream_order_manager",
        executable="order_manager",
        name=LaunchConfiguration("node_name"),
        output="screen",
    )

    return LaunchDescription(args + [order_manager_node])
