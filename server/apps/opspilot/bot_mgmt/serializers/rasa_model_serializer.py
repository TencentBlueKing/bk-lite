from apps.opspilot.models import RasaModel
from config.drf.serializers import I18nSerializer


class RasaModelSerializer(I18nSerializer):
    class Meta:
        model = RasaModel
        fields = "__all__"
