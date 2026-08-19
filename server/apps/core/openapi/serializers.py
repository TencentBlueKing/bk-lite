"""暴露专用 serializer 基类。

契约要求（design.md 3.4.2 / 3.8）：
- 暴露函数必须使用暴露专用 serializer，schema 之外的字段一律拒绝，
  客户端因此没有任何途径把身份字段混入请求；
- 分页统一 page（1-based）/ page_size（默认 20、上限 500），越限钳制而非报错。
"""

from rest_framework import serializers


class OpenAPIRequestSerializer(serializers.Serializer):
    """未知字段一律拒绝的请求基类。"""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {name: ["unknown field"] for name in sorted(unknown)}
                )
        return super().to_internal_value(data)


class PaginatedRequestSerializer(OpenAPIRequestSerializer):
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=20)

    def validate_page(self, value):
        return max(int(value), 1)

    def validate_page_size(self, value):
        return min(max(int(value), 1), 500)
