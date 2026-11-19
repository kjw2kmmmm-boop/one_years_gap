from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _find_backend_app_dir() -> tuple[str, str]:
    """워크스페이스 내 backend/app 경로와 .venv uvicorn 실행 파일 경로를 찾는다."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "backend" / "app"
        if candidate.is_dir():
            uvicorn_bin = parent / "backend" / ".venv" / "bin" / "uvicorn"
            return str(candidate), str(uvicorn_bin)
    return "/home/ubuntu/one_years_gap/icecream/backend/app", "/home/ubuntu/one_years_gap/icecream/backend/.venv/bin/uvicorn"


def generate_launch_description():
    backend_app_dir, uvicorn_bin = _find_backend_app_dir()

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
        DeclareLaunchArgument(
            "with_motion_manager",
            default_value="true",
            description="Launch icecream_motion_manager node (true | false)",
        ),
        DeclareLaunchArgument(
            "with_system_status",
            default_value="true",
            description="Launch icecream_system_status node (true | false)",
        ),
        DeclareLaunchArgument(
            "with_order_manager",
            default_value="true",
            description="Launch icecream_order_manager node (true | false)",
        ),
        DeclareLaunchArgument(
            "with_backend",
            default_value="false",
            description="Also launch FastAPI backend server (true | false)",
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
        condition=IfCondition(LaunchConfiguration("with_motion_manager")),
    )

    system_status_node = Node(
        package="icecream_system_status",
        executable="system_status",
        name="system_status_node",
        output="screen",
        additional_env={
            "ROBOT_ID": robot_id,
        },
        condition=IfCondition(LaunchConfiguration("with_system_status")),
    )

    order_manager_node = Node(
        package="icecream_order_manager",
        executable="order_manager",
        name="icecream_order_manager",
        output="screen",
        condition=IfCondition(LaunchConfiguration("with_order_manager")),
    )

    backend_process = ExecuteProcess(
        cmd=[
            uvicorn_bin,
            "main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        cwd=backend_app_dir,
        output="screen",
        condition=IfCondition(LaunchConfiguration("with_backend")),
    )

    return LaunchDescription(
        args + [
            motion_manager_node,
            system_status_node,
            order_manager_node,
            backend_process,
        ]
    )
