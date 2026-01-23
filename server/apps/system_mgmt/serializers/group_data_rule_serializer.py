from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import GroupDataRule


class GroupDataRuleSerializer(UsernameSerializer):
    class Meta:
        model = GroupDataRule
        fields = "__all__"
