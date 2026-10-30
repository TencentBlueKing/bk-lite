from django.db import models


class UserFieldType(models.TextChoices):
    TEXT = "text", "文本"
    NUMBER = "number", "数字"
    DATE = "date", "日期"


class UserFieldDefinition(models.Model):
    name = models.CharField(max_length=64)
    key = models.CharField(max_length=64, unique=True)
    field_type = models.CharField(max_length=16, choices=UserFieldType.choices)
    description = models.TextField(blank=True, default="")
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]


class UserFieldValue(models.Model):
    user = models.ForeignKey("system_mgmt.User", on_delete=models.CASCADE, related_name="field_values")
    field = models.ForeignKey(UserFieldDefinition, on_delete=models.PROTECT, related_name="values")
    value = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        unique_together = ("user", "field")
