"""脚本参数处理服务

处理位置参数格式的脚本参数：
[
    {"name": "传递路径", "value": "/tmp", "is_modified": True},
    {"name": "重试次数", "value": "", "is_modified": False},  # 脚本库模式按顺序回填默认值
]

执行时仅使用 value，并严格按列表顺序拼接为位置参数。
"""

import shlex

from rest_framework import serializers

from apps.job_mgmt.services.param_crypto import ParamCrypto
from apps.job_mgmt.utils.i18n import job_message


class ScriptParamsService:
    """脚本参数处理服务"""

    @staticmethod
    def validate_params_format(params: list, require_is_modified: bool = True, request=None) -> None:
        """
        验证 params 格式是否正确

        Args:
            params: 参数列表
            require_is_modified: 是否要求 is_modified 字段
            request: 可选请求，用于选择语言

        Raises:
            serializers.ValidationError: 格式不正确时抛出
        """
        if not isinstance(params, list):
            raise serializers.ValidationError({"params": job_message(request, "error.params_must_be_list", "Parameters must be a list")})

        for i, param in enumerate(params):
            index = i + 1
            if not isinstance(param, dict):
                raise serializers.ValidationError(
                    {
                        "params": job_message(
                            request,
                            "error.params_item_must_be_dict",
                            "Parameter {index} must be an object",
                            index=index,
                        )
                    }
                )

            required_keys = {"value"}
            if require_is_modified:
                required_keys.add("is_modified")
            missing_keys = required_keys - set(param.keys())
            if missing_keys:
                raise serializers.ValidationError(
                    {
                        "params": job_message(
                            request,
                            "error.params_item_missing_fields",
                            "Parameter {index} is missing fields: {fields}",
                            index=index,
                            fields=missing_keys,
                        )
                    }
                )

            # name 为展示字段；兼容历史 key 字段
            display_name = param.get("name", param.get("key"))
            if display_name is not None and not isinstance(display_name, str):
                raise serializers.ValidationError(
                    {
                        "params": job_message(
                            request,
                            "error.params_name_must_be_string",
                            "Parameter {index} name must be a string",
                            index=index,
                        )
                    }
                )

            if "is_modified" in param and not isinstance(param.get("is_modified"), bool):
                raise serializers.ValidationError(
                    {
                        "params": job_message(
                            request,
                            "error.params_is_modified_must_be_bool",
                            "Parameter {index} is_modified must be a boolean",
                            index=index,
                        )
                    }
                )

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
        request=None,
    ) -> list:
        """
        解析参数，将 is_modified=False 的参数替换为脚本库默认值

        Args:
            params: 位置参数列表
            script: Script 模型实例（脚本库模式时提供）
            allow_unmodified_without_script: 临时脚本模式下是否允许 is_modified=False
            request: 可选请求，用于选择语言

        Returns:
            list: 解析后的参数列表（按原顺序）

        Raises:
            serializers.ValidationError: 参数解析失败时抛出
        """
        if not params:
            return []

        # 验证格式：临时输入脚本模式可不传 is_modified
        ScriptParamsService.validate_params_format(params, require_is_modified=script is not None, request=request)

        # 获取脚本库默认参数定义（按顺序）
        default_params = ScriptParamsService.get_script_default_params(script)
        has_script = script is not None
        if has_script and default_params:
            # 执行时使用真实默认值：对 is_encrypted=true 的 default 做临时解密
            default_params = [param_def.copy() for param_def in default_params]
            ParamCrypto.decrypt_param_defaults(default_params)

        resolved_params = []
        for index, param in enumerate(params):
            name = param.get("name", param.get("key", ""))
            value = param["value"]
            is_modified = param.get("is_modified", True)
            display_index = index + 1

            if not is_modified:
                if has_script:
                    # 脚本库模式：按位置回填默认值
                    if index >= len(default_params):
                        raise serializers.ValidationError(
                            {
                                "params": job_message(
                                    request,
                                    "error.params_default_unavailable",
                                    "Parameter {index} cannot obtain a default value from the script library by position",
                                    index=display_index,
                                )
                            }
                        )
                    value = default_params[index].get("default", "")
                elif not allow_unmodified_without_script:
                    # 临时脚本模式且不允许 is_modified=False
                    raise serializers.ValidationError(
                        {
                            "params": job_message(
                                request,
                                "error.params_temp_no_default",
                                "Temporary scripts cannot use the default value for parameter {index}",
                                index=display_index,
                            )
                        }
                    )
                # 临时脚本模式且允许：直接使用前端传的 value

            # 必填校验：脚本库定义 is_required=true 的参数最终值不能为空
            if has_script and index < len(default_params):
                if default_params[index].get("is_required") and (value is None or str(value) == ""):
                    display_name = (
                        name
                        or default_params[index].get("name")
                        or job_message(request, "error.params_nth", "parameter {index}", index=display_index)
                    )
                    raise serializers.ValidationError(
                        {
                            "params": job_message(
                                request,
                                "error.params_required_empty",
                                'Parameter "{name}" is required and cannot be empty',
                                name=display_name,
                            )
                        }
                    )

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

        对每个值做 shell 引用（shlex.quote），使空值以 '' 占位、含空格/特殊
        字符的值保持完整。这样执行端再 shlex.split 还原时不会丢失空参数，
        从而避免「中间空参数被吞掉导致后续参数位置前移」的问题。

        Args:
            params: 参数列表

        Returns:
            str: 空格分隔且逐值引用的参数字符串，如 "value1 '' 'value 3'"
        """
        if not params:
            return ""

        values = [str(param.get("value", "")) for param in params]
        return " ".join(shlex.quote(v) for v in values)

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
