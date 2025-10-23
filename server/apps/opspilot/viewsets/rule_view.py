from django_filters import filters
from django_filters.rest_framework import FilterSet

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.opspilot.models import SkillRule
from apps.opspilot.serializers.rule_serializer import RuleSerializer


class ObjFilter(FilterSet):
    skill_id = filters.NumberFilter(field_name="skill_id", lookup_expr="exact")
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")


class RuleViewSet(MaintainerViewSet):
    serializer_class = RuleSerializer
    queryset = SkillRule.objects.all()
    filterset_class = ObjFilter

    @HasPermission("skill_rule-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("skill_rule-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("skill_rule-Setting")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("skill_rule-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
