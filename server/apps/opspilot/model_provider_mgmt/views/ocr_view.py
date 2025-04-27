from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.model_provider_mgmt.serializers.ocr_serializer import OCRProviderSerializer
from apps.opspilot.models import OCRProvider


class OCRProviderViewSet(AuthViewSet):
    queryset = OCRProvider.objects.all()
    serializer_class = OCRProviderSerializer
    permission_key = "provider.orc_model"
