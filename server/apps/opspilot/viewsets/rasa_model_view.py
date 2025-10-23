from rest_framework.viewsets import ModelViewSet

from apps.opspilot.models import RasaModel
from apps.opspilot.serializers.rasa_model_serializer import RasaModelSerializer


class RasaModelViewSet(ModelViewSet):
    serializer_class = RasaModelSerializer
    queryset = RasaModel.objects.all()
