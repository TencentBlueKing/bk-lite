from rest_framework import serializers

from apps.cmdb.models.change_record import ChangeRecord


class ChangeRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChangeRecord
        fields = (
            "id",
            "inst_id",
            "inst_uuid",
            "model_id",
            "label",
            "type",
            "before_data",
            "after_data",
            "attribute_snapshot",
            "operator",
            "created_at",
            "model_object",
            "message",
            "scenario",
        )
        read_only_fields = ("id", "created_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        locale = getattr(getattr(request, "user", None), "locale", None) if request else None
        from apps.cmdb.language.service import model_object_display_name

        data["model_object"] = model_object_display_name(data.get("model_object"), locale)
        return data
