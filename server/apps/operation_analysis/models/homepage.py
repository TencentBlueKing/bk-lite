"""登录首页偏好。

个人配置按 username + domain 存，不按组织拆。
没有个人行表示跟随全局。全局没有行，或 mode 为 workbench，表示应用工作台。
"""

from django.db import models


class HomepagePreference(models.Model):
    SCOPE_GLOBAL = "global"
    SCOPE_USER = "user"
    SCOPE_CHOICES = (
        (SCOPE_GLOBAL, "全局"),
        (SCOPE_USER, "个人"),
    )

    MODE_WORKBENCH = "workbench"
    MODE_DASHBOARD = "dashboard"
    MODE_CHOICES = (
        (MODE_WORKBENCH, "应用工作台"),
        (MODE_DASHBOARD, "仪表盘"),
    )

    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES)
    username = models.CharField(max_length=150, blank=True, default="")
    domain = models.CharField(max_length=100, blank=True, default="")
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_WORKBENCH)
    dashboard_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "operation_analysis_homepage_preference"
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "username", "domain"],
                name="uniq_ops_homepage_owner",
            ),
        ]
        indexes = [
            models.Index(fields=["dashboard_id"], name="idx_ops_homepage_dashboard"),
        ]

    def __str__(self):
        return f"{self.scope}:{self.username}@{self.domain}:{self.mode}"
