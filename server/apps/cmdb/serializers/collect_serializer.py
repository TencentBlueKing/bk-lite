# -- coding: utf-8 --
# @File: collect_serializer.py
# @Time: 2025/3/3 13:58
# @Author: windyzhao
from rest_framework import serializers
from rest_framework.fields import empty

from apps.cmdb.constants import VIEW, OPERATE
from apps.cmdb.models.collect_model import CollectModels, OidMapping
from apps.cmdb.utils.base import get_cmdb_rules
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.serializers import UsernameSerializer


class CollectModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollectModels
        fields = "__all__"
        extra_kwargs = {
            # "name": {"required": True},
            # "task_type": {"required": True},
        }


class CollectModelLIstSerializer(UsernameSerializer):
    message = serializers.SerializerMethodField()
    permission = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super(CollectModelLIstSerializer, self).__init__(instance, data, **kwargs)
        self.permission_map = {}
        try:
            self.set_permission_map(kwargs.get("context", {}).get("request"))
        except Exception as err:
            import traceback
            logger.error("规则格式话权限失败: {}".format(traceback.format_exc()))

    def set_permission_map(self, request):
        rules = get_cmdb_rules(request)
        for task_type, permission_data in rules.items():
            _map_data = {
                "select_all": False,
                "permission_map": {}
            }
            for data in permission_data:
                if data["id"] in ["0"]:
                    _map_data["select_all"] = True
                    _map_data["permission_map"] = data["permission"]
                    break
                _map_data["permission_map"][data["id"]] = data["permission"]
            self.permission_map[task_type] = _map_data

    class Meta:
        model = CollectModels
        fields = ["id", "name", "task_type", "driver_type", "model_id", "exec_status", "updated_at", "message",
                  "exec_time", "created_by", "input_method", "examine", "params", "permission"]

    @staticmethod
    def get_message(instance):
        if instance.collect_digest:
            return instance.collect_digest

        data = {
            "add": 0,
            "update": 0,
            "delete": 0,
            "association": 0,
        }
        return data

    def get_permission(self, obj):
        try:
            if obj.created_by == self.context["request"].user.username or not self.permission_map:
                return [VIEW, OPERATE]
            if obj.task_type not in self.permission_map:
                return []
            permission_data = self.permission_map[obj.task_type]
            if not permission_data:
                return []
            if permission_data["select_all"]:
                return permission_data["permission_map"]
            return permission_data["permission_map"].get(str(obj.id), [])
        except Exception as err:
            import traceback
            logger.error("配置采集任务补充权限失败: {}".format(traceback.format_exc()))
            return []


class OidModelSerializer(UsernameSerializer):
    class Meta:
        model = OidMapping
        fields = "__all__"
        extra_kwargs = {}
