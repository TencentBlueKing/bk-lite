from typing import Any, Optional

from rest_framework import serializers

from apps.mlops.utils.i18n import serializer_message

SERVING_PORT_MIN = 1024
SERVING_PORT_MAX = 65535
SERVING_PORT_BLOCKLIST = frozenset({22, 80, 443, 3306, 5432, 6379, 27017, 8080})
SERVING_PORT_INVALID = "error.serving_port_invalid"


def parse_serving_port(value: Any) -> Optional[int]:
    """解析用户指定的 Serving 端口。None/空表示自动分配。"""
    if value is None or value == "":
        return None
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(SERVING_PORT_INVALID) from exc
    if port < SERVING_PORT_MIN or port > SERVING_PORT_MAX or port in SERVING_PORT_BLOCKLIST:
        raise ValueError(SERVING_PORT_INVALID)
    return port


class ServingPortValidationMixin:
    """为 Serving serializer 提供 port 字段校验。"""

    def validate_port(self, value):
        try:
            return parse_serving_port(value)
        except ValueError as exc:
            raise serializers.ValidationError(serializer_message(self, str(exc) or SERVING_PORT_INVALID)) from exc
