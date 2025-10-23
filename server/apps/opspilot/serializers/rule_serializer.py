from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import SkillRule


class RuleSerializer(UsernameSerializer):
    class Meta:
        model = SkillRule
        fields = "__all__"
