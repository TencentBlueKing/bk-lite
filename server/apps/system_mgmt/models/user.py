from django.db import models


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

    class Meta:
        unique_together = ("username", "domain")

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
        ]


class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    parent_id = models.IntegerField(default=0)
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
