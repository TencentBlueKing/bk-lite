from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import BotConversationHistory


class HistorySerializer(UsernameSerializer):
    class Meta:
        model = BotConversationHistory
        fields = "__all__"
