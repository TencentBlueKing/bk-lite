from rest_framework import serializers

from apps.mlops.models import AlgorithmConfig


class AlgorithmConfigSerializer(serializers.ModelSerializer):
    """算法配置序列化器"""

    algorithm_type_display = serializers.CharField(
        source="get_algorithm_type_display", read_only=True
    )

    class Meta:
        model = AlgorithmConfig
        fields = "__all__"
        extra_kwargs = {
            "created_by": {"read_only": True},
            "updated_by": {"read_only": True},
        }

    def validate_form_config(self, value):
        """
        验证 form_config 的基本结构
        """
        if not value:
            return value

        # 基本结构检查
        if not isinstance(value, dict):
            raise serializers.ValidationError("form_config 必须是一个对象")

        # 验证 hyperopt_config 结构（如果存在）
        if "hyperopt_config" in value:
            hyperopt = value["hyperopt_config"]
            if not isinstance(hyperopt, list):
                raise serializers.ValidationError("hyperopt_config 必须是一个数组")
            for item in hyperopt:
                if not isinstance(item, dict):
                    raise serializers.ValidationError(
                        "hyperopt_config 中的每项必须是对象"
                    )
                if "key" not in item:
                    raise serializers.ValidationError(
                        "hyperopt_config 中的每项必须包含 key 字段"
                    )

        return value


class AlgorithmConfigListSerializer(serializers.ModelSerializer):
    """算法配置列表序列化器 - 用于下拉选择，不返回完整的 form_config"""

    algorithm_type_display = serializers.CharField(
        source="get_algorithm_type_display", read_only=True
    )

    class Meta:
        model = AlgorithmConfig
        fields = [
            "id",
            "algorithm_type",
            "algorithm_type_display",
            "name",
            "display_name",
            "scenario_description",
            "image",
            "is_active",
            "created_at",
            "updated_at",
        ]
