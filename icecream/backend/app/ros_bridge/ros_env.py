import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ROS_SETUP = "/opt/ros/jazzy/setup.bash"
_DEFAULT_WS_SETUP = str(_PROJECT_ROOT / "ws_dsr" / "install" / "setup.bash")
_DEFAULT_ROS_PYTHON = "/usr/bin/python3"


def get_ros_runtime_paths() -> tuple[str, str, str]:
    """ROS2 setup 스크립트와 Python 3.12 실행 경로를 반환한다."""
    ros_setup = os.getenv("ROS_SETUP_SCRIPT", _DEFAULT_ROS_SETUP)
    ws_setup = os.getenv("WS_DSR_SETUP_SCRIPT", _DEFAULT_WS_SETUP)
    ros_python = os.getenv("ROS_PYTHON_BIN", _DEFAULT_ROS_PYTHON)
    return ros_setup, ws_setup, ros_python
