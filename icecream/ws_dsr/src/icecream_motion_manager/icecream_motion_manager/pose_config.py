import os
from pathlib import Path
from typing import Any

import yaml

try:
    from ament_index_python.packages import get_package_share_directory
except ImportError:  # pragma: no cover
    get_package_share_directory = None


def resolve_poses_yaml_path() -> Path:
    """poses.yaml 파일 경로를 우선순위에 따라 찾는다."""
    env_path = os.getenv("ICECREAM_POSES_YAML")
    if env_path:
        path = Path(env_path).expanduser()
        if path.is_file():
            return path
        raise FileNotFoundError(f"ICECREAM_POSES_YAML 경로에 파일이 없습니다: {path}")

    if get_package_share_directory is not None:
        try:
            share_path = Path(get_package_share_directory("icecream_motion_manager")) / "config" / "poses.yaml"
            if share_path.is_file():
                return share_path
        except Exception:
            pass

    source_path = Path(__file__).resolve().parents[1] / "config" / "poses.yaml"
    if source_path.is_file():
        return source_path

    raise FileNotFoundError("icecream_motion_manager의 config/poses.yaml 파일을 찾을 수 없습니다.")


def load_poses_config() -> dict[str, Any]:
    """poses.yaml 내용을 읽어 dict로 반환한다."""
    yaml_path = resolve_poses_yaml_path()
    with yaml_path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"poses.yaml 형식이 올바르지 않습니다: {yaml_path}")
    return data


def get_motion_entry(section: str, pose_key: str = "pose") -> tuple[list[float], float, float]:
    """지정 섹션의 좌표(6축 float 리스트), 속도, 가속도를 반환한다."""
    cfg = load_poses_config()
    entry = cfg.get(section)
    if not isinstance(entry, dict):
        raise KeyError(f"poses.yaml에 '{section}' 섹션이 없습니다.")

    coords = entry.get(pose_key)
    if not isinstance(coords, list) or len(coords) != 6:
        raise ValueError(f"poses.yaml '{section}.{pose_key}'는 6개 숫자 리스트여야 합니다.")

    vel = float(entry["vel"])
    acc = float(entry["acc"])
    return [float(v) for v in coords], vel, acc


def get_flavor_entry(flavor: str) -> tuple[str, list[float], float, float]:
    """맛 식별자('CHOCO', 'STRAWBERRY', '초코', '딸기', '1', '2')에 해당하는 (표시명, 좌표, vel, acc)를 반환한다."""
    cfg = load_poses_config()
    flavors_cfg = cfg.get("flavors")
    if not isinstance(flavors_cfg, dict) or not isinstance(flavors_cfg.get("items"), dict):
        raise KeyError("poses.yaml에 'flavors.items' 설정이 없습니다.")

    items: dict[str, Any] = flavors_cfg["items"]
    normalized = flavor.strip().upper()

    matched_item = None
    for key, item in items.items():
        aliases = [str(a).strip().upper() for a in item.get("aliases", [key])]
        if normalized == str(key).strip().upper() or normalized in aliases:
            matched_item = item
            break

    if matched_item is None:
        supported = ", ".join(items.keys())
        raise ValueError(f"지원하지 않는 맛입니다: {flavor!r} (지원: {supported})")

    coords = matched_item.get("pose")
    if not isinstance(coords, list) or len(coords) != 6:
        raise ValueError(f"poses.yaml 맛 좌표가 올바르지 않습니다: {flavor!r}")

    label = str(matched_item.get("label", normalized))
    vel = float(matched_item.get("vel", flavors_cfg["vel"]))
    acc = float(matched_item.get("acc", flavors_cfg["acc"]))
    return label, [float(v) for v in coords], vel, acc


def get_section_config(section: str) -> dict[str, Any]:
    """지정 섹션의 설정 딕셔너리를 반환한다."""
    cfg = load_poses_config()
    entry = cfg.get(section)
    if not isinstance(entry, dict):
        raise KeyError(f"poses.yaml에 '{section}' 섹션이 없습니다.")
    return entry
