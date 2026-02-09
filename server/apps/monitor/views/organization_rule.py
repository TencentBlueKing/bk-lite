from rest_framework import viewsets

from apps.core.utils.web_utils import WebUtils
from apps.monitor.filters.monitor_object import MonitorObjectOrganizationRuleFilter
from apps.monitor.models import MonitorObjectOrganizationRule
from apps.monitor.serializers.monitor_object import MonitorObjectOrganizationRuleSerializer
from apps.monitor.services.organization_rule import OrganizationRule
from config.drf.pagination import CustomPageNumberPagination


class MonitorObjectOrganizationRuleViewSet(viewsets.ModelViewSet):
    queryset = MonitorObjectOrganizationRule.objects.all()
    serializer_class = MonitorObjectOrganizationRuleSerializer
    filterset_class = MonitorObjectOrganizationRuleFilter
    pagination_class = CustomPageNumberPagination

    def destroy(self, request, *args, **kwargs):
        del_instance_org = request.query_params.get('del_instance_org', "false").lower() in ['true', '1', 'yes']
        OrganizationRule.del_organization_rule(rule_id=kwargs.get('pk'), del_instance_org=del_instance_org)
        return WebUtils.response_success()
