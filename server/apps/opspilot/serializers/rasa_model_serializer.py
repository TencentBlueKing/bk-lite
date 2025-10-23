from apps.core.utils.serializers import I18nSerializer
from apps.opspilot.models import RasaModel


class RasaModelSerializer(I18nSerializer):
    class Meta:
        model = RasaModel
        fields = "__all__"
