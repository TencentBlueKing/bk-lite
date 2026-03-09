"""脚本参数处理服务

处理新格式的脚本参数：
[
    {"key": "param1", "value": "value1", "is_modified": True},
    {"key": "param2", "value": "******", "is_modified": False},  # 使用脚本库默认值
]
"""

from rest_framework import serializers


class ScriptParamsService:
    """脚本参数处理服务"""

    @staticmethod
    def validate_params_format(params: list) -> None:
        """
        验证 params 格式是否正确

        Args:
            params: 参数列表

        Raises:
            serializers.ValidationError: 格式不正确时抛出
        """
        if not isinstance(params, list):
            raise serializers.ValidationError({"params": "参数必须是列表格式"})

        for i, param in enumerate(params):
            if not isinstance(param, dict):
                raise serializers.ValidationError({"params": f"第 {i + 1} 个参数必须是字典格式"})

            required_keys = {"key", "value", "is_modified"}
            missing_keys = required_keys - set(param.keys())
            if missing_keys:
                raise serializers.ValidationError({"params": f"第 {i + 1} 个参数缺少字段: {missing_keys}"})

            if not isinstance(param.get("key"), str):
                raise serializers.ValidationError({"params": f"第 {i + 1} 个参数的 key 必须是字符串"})

            if not isinstance(param.get("is_modified"), bool):
                raise serializers.ValidationError({"params": f"第 {i + 1} 个参数的 is_modified 必须是布尔值"})

    @staticmethod
    def get_script_default_params(script) -> dict:
        """
        获取脚本库中脚本的默认参数映射

        Args:
            script: Script 模型实例

        Returns:
            dict: {param_name: default_value}
        """
        if not script or not script.params:
            return {}

        default_params = {}
        for param_def in script.params:
            if isinstance(param_def, dict) and "name" in param_def:
                default_params[param_def["name"]] = param_def.get("default", "")

        return default_params

    @staticmethod
    def resolve_params(
        params: list,
        script=None,
        allow_unmodified_without_script: bool = True,
    ) -> list:
        """
        解析参数，将 is_modified=False 的参数替换为脚本库默认值

        Args:
            params: 新格式的参数列表
            script: Script 模型实例（脚本库模式时提供）
            allow_unmodified_without_script: 临时脚本模式下是否允许 is_modified=False

        Returns:
            list: 解析后的参数列表，所有 value 都已填充正确值

        Raises:
            serializers.ValidationError: 参数解析失败时抛出
        """
        if not params:
            return []

        # 验证格式
        ScriptParamsService.validate_params_format(params)

        # 获取脚本库默认参数
        default_params = ScriptParamsService.get_script_default_params(script)
        has_script = script is not None

        resolved_params = []
        for param in params:
            key = param["key"]
            value = param["value"]
            is_modified = param["is_modified"]

            if not is_modified:
                if has_script:
                    # 脚本库模式：从脚本库获取默认值
                    if key not in default_params:
                        raise serializers.ValidationError({"params": f"参数 '{key}' 在脚本库中不存在，无法获取默认值"})
                    value = default_params[key]
                elif not allow_unmodified_without_script:
                    # 临时脚本模式且不允许 is_modified=False
                    raise serializers.ValidationError({"params": f"临时脚本模式下参数 '{key}' 不能使用默认值"})
                # 临时脚本模式且允许：直接使用前端传的 value

            resolved_params.append(
                {
                    "key": key,
                    "value": value,
                    "is_modified": is_modified,
                }
            )

        return resolved_params

    @staticmethod
    def params_to_string(params: list) -> str:
        """
        将参数列表转换为命令行参数字符串

        Args:
            params: 参数列表

        Returns:
            str: 空格分隔的参数字符串，如 "value1 value2 value3"
        """
        if not params:
            return ""

        values = [str(param.get("value", "")) for param in params]
        return " ".join(values)

    @staticmethod
    def params_to_dict(params: list) -> dict:
        """
        将参数列表转换为字典（用于 Jinja2 模板渲染）

        Args:
            params: 参数列表

        Returns:
            dict: {key: value}
        """
        if not params:
            return {}

        return {param["key"]: param["value"] for param in params}
