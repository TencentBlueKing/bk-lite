from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


SENSITIVE_TYPE_LABELS = {
    "email": "用户邮箱",
    "phone": "用户手机号",
}
SENSITIVE_TYPE_ORDER = tuple(SENSITIVE_TYPE_LABELS.keys())


def normalize_sensitive_types(sensitive_types):
    if not sensitive_types:
        return []

    normalized = set()
    for sensitive_type in sensitive_types:
        if isinstance(sensitive_type, str):
            value = sensitive_type.strip()
            if value in SENSITIVE_TYPE_LABELS:
                normalized.add(value)

    return [sensitive_type for sensitive_type in SENSITIVE_TYPE_ORDER if sensitive_type in normalized]


def get_authorized_types_text(sensitive_types):
    normalized_types = normalize_sensitive_types(sensitive_types)
    return "、".join(SENSITIVE_TYPE_LABELS[sensitive_type] for sensitive_type in normalized_types)


class SensitiveInfoAuthorization(TimeInfo, MaintainerInfo):
    username = models.CharField(max_length=100)
    sensitive_types = models.JSONField(default=list, blank=True)
    remark = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        unique_together = ("username", "domain")
        indexes = [
            models.Index(fields=["username", "domain"], name="system_mgmt_sensiauth_user_dom"),
        ]
