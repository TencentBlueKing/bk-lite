# -- coding: utf-8 --
import hashlib
import re

from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo

PLUGIN_ID_PATTERN = re.compile(r"^custom_[a-z0-9_]{2,40}$")
MAX_SCRIPT_BYTES = 64 * 1024
OS_LINUX = "linux"
OS_WINDOWS = "windows"
ALLOWED_OS_TYPES = (OS_LINUX, OS_WINDOWS)
SHELL_BY_OS = {
    OS_LINUX: ("bash", "sh"),
    OS_WINDOWS: ("powershell", "bat"),
}


def script_checksum(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class CustomCollectPlugin(MaintainerInfo, TimeInfo):
    """用户自定义采集插件：脚本与目标模型。"""

    name = models.CharField(max_length=128, help_text="显示名")
    plugin_id = models.CharField(max_length=48, unique=True, help_text="全局唯一标识，创建后不可改")
    model_id = models.CharField(max_length=64, help_text="目标 CMDB 模型")
    os_type = models.CharField(max_length=16, help_text="linux 或 windows，创建后不可改")
    shell = models.CharField(max_length=16, help_text="脚本解释器")
    content = models.TextField(help_text="脚本正文")
    content_checksum = models.CharField(max_length=80, help_text="脚本 sha256")
    version = models.PositiveIntegerField(default=1, help_text="脚本版本，正文变更时递增")
    desc = models.CharField(max_length=512, blank=True, default="", help_text="描述")
    team = JSONField(default=list, help_text="关联组织")

    class Meta:
        verbose_name = "自定义采集插件"

    def audit_snapshot(self):
        """变更记录只保留版本与校验和，不包含脚本正文。"""
        return {
            "plugin_id": self.plugin_id,
            "version": self.version,
            "content_checksum": self.content_checksum,
        }
