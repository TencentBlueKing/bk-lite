"""
MLOps 公共校验函数
"""

from typing import Optional

from rest_framework import status
from rest_framework.response import Response


def validate_serving_status_change(instance, new_status: str) -> Optional[Response]:
    """
    校验 serving status 变更：容器未运行时不允许设置 status=active

    Args:
        instance: Serving 实例（需要有 container_info 属性）
        new_status: 请求中的新 status 值

    Returns:
        Response: 校验失败时返回错误响应
        None: 校验通过
    """
    if new_status == "active":
        container_info = instance.container_info or {}
        if container_info.get("state") != "running":
            return Response(
                {"error": "无法将状态设为 active：容器未运行，请先启动服务"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    return None
