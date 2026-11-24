from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import ErrorLog
from apps.system_mgmt.utils.error_log_presentation import console_app_id, present_error_log
from apps.system_mgmt.utils.operation_log_utils import app_display_name_map


class ErrorLogSerializer(serializers.ModelSerializer):
    app_name = serializers.SerializerMethodField()
    recorded_text = serializers.SerializerMethodField()
    parsed = serializers.SerializerMethodField()
    method = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    exception_type = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    stack_text = serializers.SerializerMethodField()

    class Meta:
        model = ErrorLog
        fields = [
            "id",
            "username",
            "app",
            "app_name",
            "module",
            "error_message",
            "recorded_text",
            "parsed",
            "method",
            "path",
            "exception_type",
            "reason",
            "stack_text",
            "stack_trace",
            "domain",
            "created_at",
        ]
        read_only_fields = fields

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance, data, **kwargs)
        locale = getattr(self.context.get("request").user, "locale", "en") if self.context.get("request") else "en"
        self.loader = LanguageLoader(app="system_mgmt", default_lang=locale)
        self._app_name_map = None
        self._presentations = {}

    def _app_names(self):
        if self._app_name_map is None:
            instances = self.instance
            if instances is None:
                names = None
            elif isinstance(instances, ErrorLog):
                names = [console_app_id(instances.app)]
            else:
                names = [console_app_id(item.app) for item in instances]
            self._app_name_map = app_display_name_map(names, loader=self.loader)
        return self._app_name_map

    def _presentation(self, obj):
        cached = self._presentations.get(id(obj))
        if cached is None:
            cached = present_error_log(
                app=obj.app,
                error_message=obj.error_message,
                stack_trace=obj.stack_trace,
                mapping=self._app_names(),
                loader=self.loader,
            )
            self._presentations[id(obj)] = cached
        return cached

    def get_app_name(self, obj):
        return self._presentation(obj).app_name

    def get_recorded_text(self, obj):
        return self._presentation(obj).recorded_text

    def get_parsed(self, obj):
        return self._presentation(obj).parsed

    def get_method(self, obj):
        return self._presentation(obj).method

    def get_path(self, obj):
        return self._presentation(obj).path

    def get_exception_type(self, obj):
        return self._presentation(obj).exception_type

    def get_reason(self, obj):
        return self._presentation(obj).reason

    def get_stack_text(self, obj):
        return self._presentation(obj).stack_text

    def to_representation(self, instance):
        data = super().to_representation(instance)
        presented = self._presentation(instance)
        data["error_message"] = presented.recorded_text
        data["stack_trace"] = presented.stack_text
        return data
