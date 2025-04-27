from apps.opspilot.models import RerankProvider
from config.drf.serializers import AuthSerializer


class RerankProviderSerializer(AuthSerializer):
    permission_key = "provider.rerank_model"

    class Meta:
        model = RerankProvider
        fields = "__all__"
