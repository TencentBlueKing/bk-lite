from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import Channel


class ChannelSerializer(UsernameSerializer):
    class Meta:
        model = Channel
        fields = "__all__"
