from apps.system_mgmt.models import GroupDataRule
from config.drf.serializers import I18nSerializer


class GroupDataRuleSerializer(I18nSerializer):
    class Meta:
        model = GroupDataRule
        fields = "__all__"
