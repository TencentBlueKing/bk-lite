"""脚本库参数定义规范化与校验。

参数定义存于 Script.params JSON，扩展字段：
- type: "text" | "enum"（缺省视为 text，兼容存量）
- options: 枚举选项列表（type=enum 时必填）
"""

from rest_framework import serializers

from apps.job_mgmt.utils.i18n import job_message

PARAM_TYPE_TEXT = "text"
PARAM_TYPE_ENUM = "enum"
ALLOWED_PARAM_TYPES = {PARAM_TYPE_TEXT, PARAM_TYPE_ENUM}


def normalize_param_type(raw) -> str:
    if raw in (None, ""):
        return PARAM_TYPE_TEXT
    return str(raw)


def normalize_script_param_definitions(params: list, *, request=None) -> list:
    """校验并规范化脚本库参数定义（原地修改后返回）。"""
    if not params:
        return params
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

        name = param.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            raise serializers.ValidationError(
                {
                    "params": job_message(
                        request,
                        "error.params_definition_name_required",
                        "Parameter {index} name is required",
                        index=index,
                    )
                }
            )
        param["name"] = name.strip()

        param_type = normalize_param_type(param.get("type"))
        if param_type not in ALLOWED_PARAM_TYPES:
            raise serializers.ValidationError(
                {
                    "params": job_message(
                        request,
                        "error.params_definition_type_invalid",
                        'Parameter "{name}" type must be text or enum',
                        name=param["name"],
                    )
                }
            )
        param["type"] = param_type

        if param_type == PARAM_TYPE_ENUM:
            if param.get("is_encrypted"):
                raise serializers.ValidationError(
                    {
                        "params": job_message(
                            request,
                            "error.params_enum_cannot_encrypt",
                            'Parameter "{name}" cannot be both enum and encrypted',
                            name=param["name"],
                        )
                    }
                )
            param["is_encrypted"] = False

            raw_options = param.get("options") or []
            if not isinstance(raw_options, list):
                raise serializers.ValidationError(
                    {
                        "params": job_message(
                            request,
                            "error.params_enum_options_invalid",
                            'Parameter "{name}" options must be a list',
                            name=param["name"],
                        )
                    }
                )
            options = []
            seen = set()
            for opt in raw_options:
                if opt is None:
                    continue
                text = str(opt).strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                options.append(text)
            if not options:
                raise serializers.ValidationError(
                    {
                        "params": job_message(
                            request,
                            "error.params_enum_options_required",
                            'Parameter "{name}" must have at least one enum option',
                            name=param["name"],
                        )
                    }
                )
            param["options"] = options

            default = param.get("default") or ""
            if default and default not in options:
                raise serializers.ValidationError(
                    {
                        "params": job_message(
                            request,
                            "error.params_enum_default_not_in_options",
                            'Parameter "{name}" default must be one of the enum options',
                            name=param["name"],
                        )
                    }
                )
        else:
            param.pop("options", None)

    return params


def assert_execution_value_allowed(param_def: dict, value, *, request=None) -> None:
    """执行入参：枚举值必须落在 options 内（空值留给必填校验）。"""
    if normalize_param_type(param_def.get("type")) != PARAM_TYPE_ENUM:
        return
    if value is None or str(value) == "":
        return
    options = param_def.get("options") or []
    if str(value) not in {str(opt) for opt in options}:
        name = param_def.get("name") or ""
        raise serializers.ValidationError(
            {
                "params": job_message(
                    request,
                    "error.params_enum_value_not_allowed",
                    'Parameter "{name}" value is not in the allowed enum options',
                    name=name,
                )
            }
        )
