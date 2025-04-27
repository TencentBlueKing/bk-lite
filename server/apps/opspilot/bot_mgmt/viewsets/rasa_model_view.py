from rest_framework.viewsets import ModelViewSet

from apps.opspilot.bot_mgmt.serializers.rasa_model_serializer import RasaModelSerializer
from apps.opspilot.models import RasaModel


class RasaModelViewSet(ModelViewSet):
    serializer_class = RasaModelSerializer
    queryset = RasaModel.objects.all()
