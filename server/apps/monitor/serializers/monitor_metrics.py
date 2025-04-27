from rest_framework import serializers

from apps.monitor.models.monitor_metrics import MetricGroup, Metric


class MetricGroupSerializer(serializers.ModelSerializer):

    # 这里定义 is_pre 但不给默认值，防止用户传递该字段
    is_pre = serializers.BooleanField(read_only=True)
    class Meta:
        model = MetricGroup
        fields = '__all__'

    def create(self, validated_data):
        """
        在创建时，手动设置 is_pre 为 False
        """
        # 手动设置 is_pre 为 False，表示用户创建的数据是非预制的
        validated_data['is_pre'] = False

        # 调用父类的 create 方法
        return super().create(validated_data)



class MetricSerializer(serializers.ModelSerializer):

    # 这里定义 is_pre 但不给默认值，防止用户传递该字段
    is_pre = serializers.BooleanField(read_only=True)

    class Meta:
        model = Metric
        fields = '__all__'

    def create(self, validated_data):
        """
        在创建时，手动设置 is_pre 为 False
        """
        # 手动设置 is_pre 为 False，表示用户创建的数据是非预制的
        validated_data['is_pre'] = False

        # 调用父类的 create 方法
        return super().create(validated_data)