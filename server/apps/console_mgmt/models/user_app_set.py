from django.db import models
from django.utils.translation import gettext_lazy as _


class UserAppSet(models.Model):
    """用户应用配置集"""

    username = models.CharField(max_length=255, verbose_name=_("用户名"), db_index=True)
    domain = models.CharField(max_length=255, verbose_name=_("域名"), db_index=True)
    app_config_list = models.JSONField(default=list, verbose_name=_("应用配置列表"))

    class Meta:
        verbose_name = _("用户应用配置集")
        verbose_name_plural = _("用户应用配置集")
        db_table = "console_mgmt_user_app_set"
        indexes = [
            models.Index(fields=["username", "domain"]),
        ]
        unique_together = [["username", "domain"]]
