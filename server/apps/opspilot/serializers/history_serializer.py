from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import BotConversationHistory


class HistorySerializer(UsernameSerializer):
    class Meta:
        model = BotConversationHistory
        fields = [
            "id",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "bot",
            "conversation_role",
            "conversation",
            "created_at",
            "channel_user",
            "citing_knowledge",
        ]
