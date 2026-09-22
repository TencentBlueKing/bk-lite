"""参数加解密服务

处理脚本/Playbook 参数中的加密字段。
- 创建/更新时：对 is_encrypted=true 的参数 default 值进行加密
- 返回前端时：隐藏 is_encrypted=true 的参数 default 值
- 更新时若收到脱敏占位符，沿用库中原密文，不当新明文写入
- 执行时：解密参数值
"""

from apps.core.mixinx import EncryptMixin

# 读接口回填占位符；写接口收到同值表示「未改，沿用原密文」
MASKED_DEFAULT = "******"


class ParamCrypto:
    """参数加解密工具类"""

    @staticmethod
    def prepare_param_defaults_for_save(params: list, existing_params: list | None = None) -> list:
        """
        保存前处理加密参数默认值。

        - 明文新值：加密后写入
        - 脱敏占位符：按参数名从 existing_params 取回原密文（已加密则不再二次加密）
        - 占位符但无对应原值：清空，避免把掩码当真实密码落库
        """
        if not params:
            return params

        existing_by_name = {p.get("name"): p for p in (existing_params or []) if isinstance(p, dict) and p.get("name")}

        for param in params:
            if not isinstance(param, dict):
                continue
            if not param.get("is_encrypted"):
                continue
            default = param.get("default")
            if not default:
                continue
            if default == MASKED_DEFAULT:
                old = existing_by_name.get(param.get("name"))
                if old and old.get("is_encrypted") and old.get("default") and old.get("default") != MASKED_DEFAULT:
                    param["default"] = old["default"]
                else:
                    param["default"] = ""
                continue
            EncryptMixin.encrypt_field("default", param)

        return params

    @staticmethod
    def encrypt_param_defaults(params: list) -> list:
        """
        加密参数定义中的默认值（无既有密文可回填的创建场景）。

        对 is_encrypted=true 的参数，加密其 default 字段；脱敏占位符不会被当作明文加密。

        Args:
            params: 参数定义列表 [{name, label, description, default, is_encrypted}, ...]

        Returns:
            处理后的参数列表（原地修改）
        """
        return ParamCrypto.prepare_param_defaults_for_save(params, existing_params=None)

    @staticmethod
    def mask_encrypted_defaults(params: list) -> list:
        """
        隐藏加密参数的默认值（用于返回前端）

        对 is_encrypted=true 的参数，将 default 替换为脱敏占位符

        Args:
            params: 参数定义列表

        Returns:
            处理后的参数列表（返回新列表，不修改原数据）
        """
        if not params:
            return params

        result = []
        for param in params:
            param_copy = param.copy()
            if param_copy.get("is_encrypted") and param_copy.get("default"):
                param_copy["default"] = MASKED_DEFAULT
            result.append(param_copy)

        return result

    @staticmethod
    def encrypt_execution_params(params: dict, param_definitions: list) -> dict:
        """
        加密执行参数值

        根据参数定义中的 is_encrypted 标记，加密对应的执行参数

        Args:
            params: 执行参数 {param_name: value, ...}
            param_definitions: 参数定义列表 [{name, is_encrypted, ...}, ...]

        Returns:
            处理后的参数字典（原地修改）
        """
        if not params or not param_definitions:
            return params

        # 构建加密字段名集合
        encrypted_fields = {p.get("name") for p in param_definitions if p.get("is_encrypted")}

        for field_name in encrypted_fields:
            if field_name in params and params[field_name]:
                EncryptMixin.encrypt_field(field_name, params)

        return params

    @staticmethod
    def decrypt_execution_params(params: dict, param_definitions: list) -> dict:
        """
        解密执行参数值（用于实际执行）

        根据参数定义中的 is_encrypted 标记，解密对应的执行参数

        Args:
            params: 执行参数 {param_name: value, ...}
            param_definitions: 参数定义列表 [{name, is_encrypted, ...}, ...]

        Returns:
            处理后的参数字典（原地修改）
        """
        if not params or not param_definitions:
            return params

        # 构建加密字段名集合
        encrypted_fields = {p.get("name") for p in param_definitions if p.get("is_encrypted")}

        for field_name in encrypted_fields:
            if field_name in params and params[field_name]:
                EncryptMixin.decrypt_field(field_name, params)

        return params

    @staticmethod
    def decrypt_param_defaults(params: list) -> list:
        """
        解密参数定义中的默认值（用于执行时填充默认值）

        Args:
            params: 参数定义列表

        Returns:
            处理后的参数列表（原地修改）
        """
        if not params:
            return params

        for param in params:
            if param.get("is_encrypted") and param.get("default"):
                EncryptMixin.decrypt_field("default", param)

        return params

    @staticmethod
    def prepare_params_for_execution(
        execution_params: dict,
        param_definitions: list,
    ) -> dict:
        """
        准备执行参数（解密 + 填充默认值）

        用于 Celery task 执行前调用

        Args:
            execution_params: 用户提交的执行参数
            param_definitions: 脚本/Playbook 的参数定义

        Returns:
            解密后可用于执行的参数字典
        """
        if not param_definitions:
            return execution_params or {}

        # 复制一份，避免修改原数据
        result = dict(execution_params) if execution_params else {}

        # 解密参数定义中的默认值（临时副本）
        decrypted_definitions = [p.copy() for p in param_definitions]
        ParamCrypto.decrypt_param_defaults(decrypted_definitions)

        # 填充默认值（如果用户未提供）
        for param_def in decrypted_definitions:
            param_name = param_def.get("name")
            if param_name and param_name not in result:
                default_value = param_def.get("default", "")
                if default_value:
                    result[param_name] = default_value

        # 解密用户提供的加密参数
        ParamCrypto.decrypt_execution_params(result, param_definitions)

        return result
