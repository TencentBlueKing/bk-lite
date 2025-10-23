from apps.core.utils.serializers import I18nSerializer
from apps.opspilot.models import BotConversationHistory


class HistorySerializer(I18nSerializer):
    class Meta:
        model = BotConversationHistory
        fields = "__all__"
