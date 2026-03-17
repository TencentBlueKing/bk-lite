"""参数加解密服务

处理脚本/Playbook 参数中的加密字段。
- 创建/更新时：对 is_encrypted=true 的参数 default 值进行加密
- 返回前端时：隐藏 is_encrypted=true 的参数 default 值
- 执行时：解密参数值
"""

from apps.core.mixinx import EncryptMixin


class ParamCrypto:
    """参数加解密工具类"""

    @staticmethod
    def encrypt_param_defaults(params: list) -> list:
        """
        加密参数定义中的默认值

        对 is_encrypted=true 的参数，加密其 default 字段

        Args:
            params: 参数定义列表 [{name, label, description, default, is_encrypted}, ...]

        Returns:
            处理后的参数列表（原地修改）
        """
        if not params:
            return params

        for param in params:
            if param.get("is_encrypted") and param.get("default"):
                EncryptMixin.encrypt_field("default", param)

        return params

    @staticmethod
    def mask_encrypted_defaults(params: list) -> list:
        """
        隐藏加密参数的默认值（用于返回前端）

        对 is_encrypted=true 的参数，将 default 替换为 ***

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
                param_copy["default"] = "******"
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
