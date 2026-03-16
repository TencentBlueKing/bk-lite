"""脚本参数处理服务

处理位置参数格式的脚本参数：
[
    {"name": "传递路径", "value": "/tmp", "is_modified": True},
    {"name": "重试次数", "value": "", "is_modified": False},  # 脚本库模式按顺序回填默认值
]

执行时仅使用 value，并严格按列表顺序拼接为位置参数。
"""

from rest_framework import serializers


class ScriptParamsService:
    """脚本参数处理服务"""

    @staticmethod
    def validate_params_format(params: list, require_is_modified: bool = True) -> None:
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

            required_keys = {"value"}
            if require_is_modified:
                required_keys.add("is_modified")
            missing_keys = required_keys - set(param.keys())
            if missing_keys:
                raise serializers.ValidationError({"params": f"第 {i + 1} 个参数缺少字段: {missing_keys}"})

            # name 为展示字段；兼容历史 key 字段
            display_name = param.get("name", param.get("key"))
            if display_name is not None and not isinstance(display_name, str):
                raise serializers.ValidationError({"params": f"第 {i + 1} 个参数的 name 必须是字符串"})

            if "is_modified" in param and not isinstance(param.get("is_modified"), bool):
                raise serializers.ValidationError({"params": f"第 {i + 1} 个参数的 is_modified 必须是布尔值"})

    @staticmethod
    def get_script_default_params(script) -> list:
        """
        获取脚本库中脚本的默认参数定义（按顺序）

        Args:
            script: Script 模型实例

        Returns:
            list: 参数定义列表
        """
        if not script or not script.params:
            return []

        return [param_def for param_def in script.params if isinstance(param_def, dict)]

    @staticmethod
    def resolve_params(
        params: list,
        script=None,
        allow_unmodified_without_script: bool = True,
    ) -> list:
        """
        解析参数，将 is_modified=False 的参数替换为脚本库默认值

        Args:
            params: 位置参数列表
            script: Script 模型实例（脚本库模式时提供）
            allow_unmodified_without_script: 临时脚本模式下是否允许 is_modified=False

        Returns:
            list: 解析后的参数列表（按原顺序）

        Raises:
            serializers.ValidationError: 参数解析失败时抛出
        """
        if not params:
            return []

        # 验证格式：临时输入脚本模式可不传 is_modified
        ScriptParamsService.validate_params_format(params, require_is_modified=script is not None)

        # 获取脚本库默认参数定义（按顺序）
        default_params = ScriptParamsService.get_script_default_params(script)
        has_script = script is not None
        if has_script and default_params:
            # 执行时使用真实默认值：对 is_encrypted=true 的 default 做临时解密
            from apps.job_mgmt.services.param_crypto import ParamCrypto

            default_params = [param_def.copy() for param_def in default_params]
            ParamCrypto.decrypt_param_defaults(default_params)

        resolved_params = []
        for index, param in enumerate(params):
            name = param.get("name", param.get("key", ""))
            value = param["value"]
            is_modified = param.get("is_modified", True)

            if not is_modified:
                if has_script:
                    # 脚本库模式：按位置回填默认值
                    if index >= len(default_params):
                        raise serializers.ValidationError({"params": f"第 {index + 1} 个参数无法从脚本库按顺序获取默认值"})
                    value = default_params[index].get("default", "")
                elif not allow_unmodified_without_script:
                    # 临时脚本模式且不允许 is_modified=False
                    raise serializers.ValidationError({"params": f"临时脚本模式下第 {index + 1} 个参数不能使用默认值"})
                # 临时脚本模式且允许：直接使用前端传的 value

            resolved_params.append(
                {
                    "name": name,
                    "value": value,
                    "is_modified": is_modified,
                }
            )

        return resolved_params

    @staticmethod
    def params_to_string(params: list) -> str:
        """
        将参数列表按顺序转换为命令行位置参数字符串

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
            dict: {name: value}
        """
        if not params:
            return {}

        return {param.get("name", param.get("key", "")): param.get("value", "") for param in params if param.get("name") or param.get("key")}
