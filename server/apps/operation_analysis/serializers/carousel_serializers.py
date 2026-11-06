from rest_framework import serializers

from apps.operation_analysis.models.carousel import (
    CAROUSEL_DEFAULT_DWELL_SECONDS,
    CAROUSEL_DWELL_MAX_SECONDS,
    CAROUSEL_DWELL_MIN_SECONDS,
    CAROUSEL_MAX_ITEMS,
    CAROUSEL_RESOURCE_TYPES,
    CanvasCarousel,
)
from apps.operation_analysis.services.user_messages import oa_message


class CanvasCarouselItemWriteSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, min_value=1)
    resource_type = serializers.ChoiceField(choices=[value for value, _label in CAROUSEL_RESOURCE_TYPES])
    canvas_id = serializers.IntegerField(min_value=1)
    dwell_seconds = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=CAROUSEL_DWELL_MIN_SECONDS,
        max_value=CAROUSEL_DWELL_MAX_SECONDS,
    )


class CanvasCarouselWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    desc = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    groups = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, allow_empty=False)
    default_dwell_seconds = serializers.IntegerField(
        required=False,
        min_value=CAROUSEL_DWELL_MIN_SECONDS,
        max_value=CAROUSEL_DWELL_MAX_SECONDS,
    )
    items = CanvasCarouselItemWriteSerializer(many=True, required=False)

    def validate_items(self, items):
        if len(items) > CAROUSEL_MAX_ITEMS:
            raise serializers.ValidationError(oa_message("messages.carousel_item_limit", "每个轮播列表最多 50 个条目"))
        return items

    def validate(self, attrs):
        request = self.context.get("request")
        if "groups" not in attrs or not attrs.get("groups"):
            if self.instance is None:
                from apps.operation_analysis.services.carousel import viewer_org_ids_from_request

                org_ids = viewer_org_ids_from_request(request) if request is not None else []
                if not org_ids:
                    raise serializers.ValidationError({"groups": oa_message("messages.carousel_groups_required", "请选择所属组织")})
                attrs["groups"] = org_ids[:1]
        if self.instance is None and "default_dwell_seconds" not in attrs:
            attrs["default_dwell_seconds"] = CAROUSEL_DEFAULT_DWELL_SECONDS
        if "desc" in attrs and attrs["desc"] is None:
            attrs["desc"] = ""
        elif self.instance is None and "desc" not in attrs:
            attrs["desc"] = ""
        return attrs


class CanvasCarouselAppendSerializer(serializers.Serializer):
    resource_type = serializers.ChoiceField(choices=[value for value, _label in CAROUSEL_RESOURCE_TYPES])
    canvas_id = serializers.IntegerField(min_value=1)
    dwell_seconds = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=CAROUSEL_DWELL_MIN_SECONDS,
        max_value=CAROUSEL_DWELL_MAX_SECONDS,
    )


class CanvasCarouselListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)
    playable_count = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()
    canvas_keys = serializers.SerializerMethodField()

    class Meta:
        model = CanvasCarousel
        fields = [
            "id",
            "name",
            "desc",
            "groups",
            "default_dwell_seconds",
            "item_count",
            "playable_count",
            "duration_seconds",
            "canvas_keys",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]

    def _playback_stat(self, carousel: CanvasCarousel, key: str) -> int:
        stats = (self.context.get("playback_stats") or {}).get(carousel.id) or {}
        return int(stats.get(key) or 0)

    def get_playable_count(self, carousel: CanvasCarousel) -> int:
        return self._playback_stat(carousel, "playable_count")

    def get_duration_seconds(self, carousel: CanvasCarousel) -> int:
        return self._playback_stat(carousel, "duration_seconds")

    def get_canvas_keys(self, carousel: CanvasCarousel) -> list[str]:
        return [f"{item.resource_type}:{item.canvas_id}" for item in carousel.items.all()]
