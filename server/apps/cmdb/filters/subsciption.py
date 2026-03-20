# -- coding: utf-8 --
# @File: subsciption.py
# @Time: 2026/3/17 14:45
# @Author: windyzhao
from django_filters import CharFilter, FilterSet
from apps.cmdb.models.subscription_rule import SubscriptionRule


class SubscriptionRuleFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains")
    search = CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = SubscriptionRule
        fields = ["name", "search"]
