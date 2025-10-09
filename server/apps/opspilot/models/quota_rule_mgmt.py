from django.db import models

from apps.core.models.time_info import TimeInfo


class QuotaRule(TimeInfo):
    name = models.CharField(max_length=100, verbose_name="Name")
    target_type = models.CharField(max_length=10, verbose_name="Target Type")
    target_list = models.JSONField(default=list, verbose_name="Target List")
    rule_type = models.CharField(max_length=10, verbose_name="Rule Type")
    file_size = models.FloatField(verbose_name="Total Size", default=0)
    unit = models.CharField(max_length=10, verbose_name="Size Unit")
    skill_count = models.IntegerField(verbose_name="Skill Count", default=0)
    bot_count = models.IntegerField(verbose_name="Bot Count", default=0)

    class Meta:
        db_table = "base_quotarule"
