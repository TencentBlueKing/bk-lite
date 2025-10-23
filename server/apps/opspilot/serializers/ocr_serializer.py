from apps.core.utils.serializers import AuthSerializer
from apps.opspilot.models import OCRProvider
from apps.opspilot.serializers.model_type_serializer import CustomProviderSerializer


class OCRProviderSerializer(AuthSerializer, CustomProviderSerializer):
    permission_key = "provider.ocr_model"

    class Meta:
        model = OCRProvider
        fields = "__all__"
