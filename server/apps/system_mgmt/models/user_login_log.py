from django.db import models

from apps.core.models.time_info import TimeInfo


class UserLoginLog(TimeInfo):
    """
    用户登录日志模型

    记录用户登录行为，包括：
    - 登录时间：使用 TimeInfo 的 created_at 字段
    - 用户名：登录使用的用户名
    - 源IP：登录来源的 IP 地址
    - 地理位置：通过 IP 地址解析的地理位置
    - 操作系统：从 User-Agent 解析的操作系统信息
    - 浏览器：从 User-Agent 解析的浏览器信息
    - 登录状态：成功或失败
    - 失败原因：如果失败，记录失败原因
    """

    # 登录状态选项
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    username = models.CharField("Username", max_length=100, db_index=True)
    source_ip = models.GenericIPAddressField("Source IP", db_index=True)
    status = models.CharField("Login Status", max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS, db_index=True)
    domain = models.CharField("Domain", max_length=100, default="domain.com", db_index=True)
    failure_reason = models.CharField("Failure Reason", max_length=255, blank=True, default="")
    user_agent = models.CharField("User Agent", max_length=500, blank=True, default="")
    os_info = models.CharField("Operating System", max_length=100, blank=True, default="")
    browser_info = models.CharField("Browser", max_length=100, blank=True, default="")
    location = models.CharField("Location", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "User Login Log"
        verbose_name_plural = "User Login Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at", "status"]),
            models.Index(fields=["username", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.username} - {self.status} - {self.created_at}"

    @staticmethod
    def display_fields():
        return [
            "id",
            "username",
            "source_ip",
            # "location",
            "os_info",
            "browser_info",
            "status",
            "domain",
            "failure_reason",
            "created_at",
        ]
