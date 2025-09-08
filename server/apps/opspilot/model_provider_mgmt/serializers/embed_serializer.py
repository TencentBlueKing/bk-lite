from apps.core.utils.serializers import AuthSerializer
from apps.opspilot.model_provider_mgmt.serializers.model_type_serializer import ProviderModelTypeSerializer
from apps.opspilot.models import EmbedProvider


class EmbedProviderSerializer(AuthSerializer, ProviderModelTypeSerializer):
    permission_key = "provider.embed_model"

    class Meta:
        model = EmbedProvider
        fields = ("name", "enabled", "team", "is_build_in", "model_type", "id", "model_type_name", "icon")
