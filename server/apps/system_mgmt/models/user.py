from django.db import models
from django.utils import timezone as django_timezone


class User(models.Model):
    username = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)
    email = models.EmailField()
    password = models.CharField(max_length=128)
    disabled = models.BooleanField(default=False)
    locale = models.CharField(max_length=32, default="zh-Hans")
    timezone = models.CharField(max_length=32, default="Asia/Shanghai")
    group_list = models.JSONField(default=list)
    role_list = models.JSONField(default=list)
    temporary_pwd = models.BooleanField(default=False)
    otp_secret = models.CharField(max_length=128, null=True, blank=True)
    domain = models.CharField(max_length=100, default="domain.com")
    last_login = models.DateTimeField(null=True, blank=True)
    password_last_modified = models.DateTimeField(default=django_timezone.now, verbose_name="密码最后修改时间")
    password_error_count = models.IntegerField(default=0, verbose_name="密码错误次数")
    account_locked_until = models.DateTimeField(null=True, blank=True, verbose_name="账号锁定截止时间")

    class Meta:
        unique_together = ("username", "domain")

    def save(self, *args, **kwargs):
        """重写save方法，自动更新password_last_modified"""
        # 如果是更新操作，检查密码是否变化
        if self.pk:
            try:
                old_instance = User.objects.get(pk=self.pk)
                # 如果密码发生变化，更新password_last_modified
                if old_instance.password != self.password:
                    self.password_last_modified = django_timezone.now()
                    self.password_error_count = 0  # 重置错误次数
                    self.account_locked_until = None  # 解除锁定
            except User.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    @staticmethod
    def display_fields():
        return [
            "id",
            "username",
            "display_name",
            "email",
            "disabled",
            "locale",
            "timezone",
            "domain",
            "role_list",
            "last_login",
            "password_last_modified",
            "password_error_count",
            "account_locked_until",
        ]


class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    parent_id = models.IntegerField(default=0, db_index=True)
    external_id = models.CharField(max_length=100, null=True, blank=True)
    roles = models.ManyToManyField("Role", blank=True, verbose_name="角色列表")
    is_virtual = models.BooleanField(default=False, verbose_name="是否虚拟组")

    class Meta:
        unique_together = ("name", "parent_id")

    @staticmethod
    def display_fields():
        return [
            "id",
            "name",
            "description",
            "parent_id",
            "external_id",
            "is_virtual",
        ]
