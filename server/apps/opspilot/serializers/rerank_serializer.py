from apps.core.utils.serializers import AuthSerializer
from apps.opspilot.models import RerankProvider
from apps.opspilot.serializers.model_type_serializer import CustomProviderSerializer


class RerankProviderSerializer(AuthSerializer, CustomProviderSerializer):
    permission_key = "provider.rerank_model"

    class Meta:
        model = RerankProvider
        fields = "__all__"
