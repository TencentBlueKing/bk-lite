from django.db import models


class GroupDataRule(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    group_id = models.CharField(max_length=100)
    group_name = models.CharField(max_length=100)
    rules = models.JSONField(default=dict)
    app = models.CharField(max_length=50, default="")

    class Meta:
        unique_together = ("name", "group_id")


class UserRule(models.Model):
    username = models.CharField(max_length=100)
    group_rule = models.ForeignKey(GroupDataRule, on_delete=models.CASCADE)
