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
    token_set = models.JSONField(default=list, verbose_name="Token Set")

    class Meta:
        db_table = "base_quotarule"


class TeamTokenUseInfo(TimeInfo):
    group = models.CharField(max_length=100, verbose_name="Group")
    llm_model = models.CharField(max_length=100, verbose_name="LLM Model")
    used_token = models.BigIntegerField(verbose_name="Used Token")

    class Meta:
        unique_together = ("group", "llm_model")
        db_table = "base_teamtokenuseinfo"
