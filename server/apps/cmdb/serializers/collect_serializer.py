# -- coding: utf-8 --
# @File: collect_serializer.py
# @Time: 2025/3/3 13:58
# @Author: windyzhao
from rest_framework import serializers
from apps.cmdb.models.collect_model import CollectModels, OidMapping


class CollectModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollectModels
        fields = "__all__"
        extra_kwargs = {
            # "name": {"required": True},
            # "task_type": {"required": True},
        }


class CollectModelLIstSerializer(serializers.ModelSerializer):
    message = serializers.SerializerMethodField()

    class Meta:
        model = CollectModels
        fields = ["id", "name", "task_type", "driver_type", "model_id", "exec_status", "updated_at", "message",
                  "exec_time", "created_by", "input_method", "examine", "params"]

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


class MidModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = OidMapping
        fields = "__all__"
        extra_kwargs = {}
