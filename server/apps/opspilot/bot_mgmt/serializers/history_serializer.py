from apps.opspilot.models import BotConversationHistory
from config.drf.serializers import I18nSerializer


class HistorySerializer(I18nSerializer):
    class Meta:
        model = BotConversationHistory
        fields = "__all__"
