from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import RasaModel


class RasaModelSerializer(UsernameSerializer):
    class Meta:
        model = RasaModel
        fields = [
            "id",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "name",
            "description",
            "model_file",
        ]
