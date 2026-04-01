from rest_framework import serializers

from apps.monitor.models.monitor_metrics import MetricGroup, Metric


class MetricGroupSerializer(serializers.ModelSerializer):
    # 这里定义 is_pre 但不给默认值，防止用户传递该字段
    is_pre = serializers.BooleanField(read_only=True)

    class Meta:
        model = MetricGroup
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        monitor_object = attrs.get("monitor_object", getattr(self.instance, "monitor_object", None))
        monitor_plugin = attrs.get("monitor_plugin", getattr(self.instance, "monitor_plugin", None))
        name = attrs.get("name", getattr(self.instance, "name", None))

        if monitor_plugin and monitor_plugin.template_type == "api" and not monitor_plugin.template_id:
            raise serializers.ValidationError({"monitor_plugin": "自建API模板配置异常"})

        queryset = MetricGroup.objects.filter(
            monitor_object=monitor_object,
            monitor_plugin=monitor_plugin,
            name=name,
        )
        if self.instance is not None:
            queryset = queryset.exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError({"name": "同模板内指标分组名称不能重复"})

        return attrs

    def create(self, validated_data):
        """
        在创建时，手动设置 is_pre 为 False
        """
        # 手动设置 is_pre 为 False，表示用户创建的数据是非预制的
        validated_data["is_pre"] = False

        # 调用父类的 create 方法
        return super().create(validated_data)


class MetricSerializer(serializers.ModelSerializer):
    # 这里定义 is_pre 但不给默认值，防止用户传递该字段
    is_pre = serializers.BooleanField(read_only=True)

    class Meta:
        model = Metric
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        monitor_object = attrs.get("monitor_object", getattr(self.instance, "monitor_object", None))
        monitor_plugin = attrs.get("monitor_plugin", getattr(self.instance, "monitor_plugin", None))
        name = attrs.get("name", getattr(self.instance, "name", None))

        queryset = Metric.objects.filter(
            monitor_object=monitor_object,
            monitor_plugin=monitor_plugin,
            name=name,
        )
        if self.instance is not None:
            queryset = queryset.exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError({"name": "同模板内指标名称不能重复"})

        return attrs

    def create(self, validated_data):
        """
        在创建时，手动设置 is_pre 为 False
        """
        # 手动设置 is_pre 为 False，表示用户创建的数据是非预制的
        validated_data["is_pre"] = False

        # 调用父类的 create 方法
        return super().create(validated_data)
