from rest_framework import serializers

from apps.opspilot.models import QuotaRule


class QuotaRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotaRule
        fields = "__all__"
