from apps.core.utils.serializers import AuthSerializer
from apps.opspilot.models import EmbedProvider
from apps.opspilot.serializers.model_type_serializer import CustomProviderSerializer


class EmbedProviderSerializer(AuthSerializer, CustomProviderSerializer):
    permission_key = "provider.embed_model"

    class Meta:
        model = EmbedProvider
        fields = "__all__"
