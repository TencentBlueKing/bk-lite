from apps.opspilot.models import OCRProvider
from config.drf.serializers import AuthSerializer


class OCRProviderSerializer(AuthSerializer):
    permission_key = "provider.orc_model"

    class Meta:
        model = OCRProvider
        fields = "__all__"
