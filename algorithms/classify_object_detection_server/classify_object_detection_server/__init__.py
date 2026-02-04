"""classify_object_detection_server package."""

from pathlib import Path


def get_project_root():
    """获取项目根目录（包含 pyproject.toml 的目录）.

    通过向上查找特征文件（pyproject.toml）来定位项目根目录，
    避免硬编码 .parent 层级。

    Returns:
        Path: 项目根目录路径
    """
    current = Path(__file__).parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: 如果找不到 pyproject.toml，返回上一级目录
    return current.parent


# 项目根目录常量（在包导入时计算一次）
PROJECT_ROOT = get_project_root()

__all__ = ["PROJECT_ROOT", "get_project_root"]
