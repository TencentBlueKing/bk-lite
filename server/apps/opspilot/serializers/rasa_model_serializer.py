from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import RasaModel


class RasaModelSerializer(UsernameSerializer):
    class Meta:
        model = RasaModel
        fields = "__all__"
