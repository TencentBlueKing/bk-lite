from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import QAPairs
from apps.opspilot.tasks import create_qa_pairs


class QAPairsSerializer(UsernameSerializer):
    class Meta:
        model = QAPairs
        fields = "__all__"

    def update(self, instance, validated_data):
        only_question = validated_data.pop("only_question", False)
        if instance.status in ["generating", "pending"]:
            raise Exception("The document is being trained, please try again later.")
        instance = super().update(instance, validated_data)
        create_qa_pairs.delay([instance.id], only_question, True)
        return instance
