from django_filters import filters
from django_filters.rest_framework import FilterSet

from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.opspilot.model_provider_mgmt.serializers.rule_serializer import RuleSerializer
from apps.opspilot.models import SkillRule


class ObjFilter(FilterSet):
    skill_id = filters.NumberFilter(field_name="skill_id", lookup_expr="exact")
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")


class RuleViewSet(MaintainerViewSet):
    serializer_class = RuleSerializer
    queryset = SkillRule.objects.all()
    filterset_class = ObjFilter
