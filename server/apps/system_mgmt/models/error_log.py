from django.db import models


class ErrorLog(models.Model):
    """
    错误日志模型

    记录系统运行过程中的错误信息，包括：
    - 时间：created_at 字段
    - 用户：触发错误的用户名
    - 应用：发生错误的应用模块
    - 模块：具体的功能模块
    - 错误信息：详细的错误描述
    """

    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_index=True, help_text="错误发生时间")
    username = models.CharField("用户名", max_length=100, db_index=True, help_text="触发错误的用户")
    app = models.CharField("应用", max_length=100, db_index=True, help_text="发生错误的应用模块")
    module = models.CharField("模块", max_length=200, db_index=True, help_text="具体的功能模块")
    error_message = models.TextField("错误信息", help_text="详细的错误描述")
    domain = models.CharField("域名", max_length=100, default="domain.com", db_index=True)

    class Meta:
        verbose_name = "错误日志"
        verbose_name_plural = "错误日志"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at", "app"]),
            models.Index(fields=["username", "-created_at"]),
            models.Index(fields=["app", "module", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.username} - {self.app} - {self.module} - {self.created_at}"

    @staticmethod
    def display_fields():
        return [
            "id",
            "username",
            "app",
            "module",
            "error_message",
            "domain",
            "created_at",
        ]
