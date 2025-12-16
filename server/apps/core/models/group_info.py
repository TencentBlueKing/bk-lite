# -- coding: utf-8 --
# @File: group_info.py
# @Time: 2025/11/5 14:09
# @Author: windyzhao
from django.db import models
from django.db.models import JSONField
from django.utils.translation import gettext_lazy as _


class Groups(models.Model):
    """
    Add time fields to another models.
    """

    class Meta:
        verbose_name = _("Group Time Fields")
        abstract = True

    groups = JSONField(help_text="组织", default=list, null=True, blank=True)
