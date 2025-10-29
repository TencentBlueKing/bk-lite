from rest_framework import viewsets

from apps.core.utils.web_utils import WebUtils
from apps.monitor.filters.monitor_object import MonitorObjectOrganizationRuleFilter
from apps.monitor.models import MonitorObjectOrganizationRule
from apps.monitor.serializers.monitor_object import MonitorObjectOrganizationRuleSerializer
from apps.monitor.services.organization_rule import OrganizationRule
from config.drf.pagination import CustomPageNumberPagination


class MonitorObjectOrganizationRuleVieSet(viewsets.ModelViewSet):
    queryset = MonitorObjectOrganizationRule.objects.all()
    serializer_class = MonitorObjectOrganizationRuleSerializer
    filterset_class = MonitorObjectOrganizationRuleFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        del_instance_org = request.query_params.get('del_instance_org', "false").lower() in ['true', '1', 'yes']
        OrganizationRule.del_organization_rule(rule_id=kwargs.get('pk'), del_instance_org=del_instance_org)
        return WebUtils.response_success()
