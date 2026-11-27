from rest_framework import serializers

from apps.job_mgmt.services.resource_organizations import SELECTION_LIMIT


class SelectionSerializer(serializers.Serializer):
    ids = serializers.ListSerializer(child=serializers.IntegerField(min_value=1, max_value=2**63 - 1), min_length=1, max_length=SELECTION_LIMIT)

    def validate_ids(self, value):
        return sorted(set(value))


class OrganizationAdjustmentSerializer(SelectionSerializer):
    operation = serializers.ChoiceField(choices=("add", "remove"))
    organization = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    preview_token = serializers.CharField(required=False, max_length=64)
    exclude_blocked = serializers.BooleanField(default=False)
