from apps.opspilot.models import EmbedProvider
from config.drf.serializers import AuthSerializer


class EmbedProviderSerializer(AuthSerializer):
    permission_key = "provider.embed_model"

    class Meta:
        model = EmbedProvider
        fields = "__all__"
