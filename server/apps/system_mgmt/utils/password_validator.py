import re
from typing import Dict, Tuple

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import SystemSettings


class PasswordValidator:
    """
    密码复杂度校验器

    根据系统设置中的密码策略进行校验：
    - 密码长度范围
    - 必须包含的字符类型（可多选）
    - 字符类型：大写字母、小写字母、数字、特殊符号
    """

    # 字符类型正则模式
    CHAR_TYPES = {
        "uppercase": r"[A-Z]",  # 大写字母
        "lowercase": r"[a-z]",  # 小写字母
        "digit": r"[0-9]",  # 数字
        "special": r'[!@#$%^&*()_+\-=\[\]{};:\'"\\|,.<>?/~`]',  # 特殊符号
    }

    # 字符类型中文名称
    CHAR_TYPE_NAMES = {
        "uppercase": "大写字母",
        "lowercase": "小写字母",
        "digit": "数字",
        "special": "特殊符号",
    }

    @classmethod
    def get_password_settings(cls) -> Dict:
        """
        从数据库获取密码策略配置

        Returns:
            dict: 密码策略配置字典
        """
        try:
            settings = SystemSettings.objects.filter(key__startswith="pwd_set_").values("key", "value")
            config = {}

            for setting in settings:
                key = setting["key"].replace("pwd_set_", "")

                # 特殊处理字符类型配置
                if key == "required_char_types":
                    # 逗号分隔的字符类型列表
                    config[key] = [t.strip() for t in setting["value"].split(",") if t.strip()]
                else:
                    try:
                        config[key] = int(setting["value"])
                    except (ValueError, TypeError):
                        logger.warning(f"无法解析配置项 {setting['key']}: {setting['value']}")

            # 设置默认值
            config.setdefault("min_length", 8)
            config.setdefault("max_length", 20)
            config.setdefault("required_char_types", ["uppercase", "lowercase", "digit", "special"])

            return config

        except Exception as e:
            logger.error(f"获取密码配置失败: {str(e)}")
            # 返回默认配置
            return {
                "min_length": 8,
                "max_length": 20,
                "required_char_types": ["uppercase", "lowercase", "digit", "special"],
            }

    @classmethod
    def validate_password(cls, password: str) -> Tuple[bool, str]:
        """
        校验密码复杂度

        Args:
            password: 待校验的密码

        Returns:
            tuple: (是否通过, 错误信息)
        """
        if not password:
            return False, "密码不能为空"

        # 获取密码策略配置
        config = cls.get_password_settings()
        min_length = config["min_length"]
        max_length = config["max_length"]
        required_types = config["required_char_types"]

        # 1. 检查密码长度
        password_length = len(password)
        if password_length < min_length:
            return False, f"密码长度不能少于{min_length}个字符"

        if password_length > max_length:
            return False, f"密码长度不能超过{max_length}个字符"

        # 2. 检查必须包含的字符类型
        missing_types = []

        for char_type in required_types:
            if char_type not in cls.CHAR_TYPES:
                logger.warning(f"未知的字符类型: {char_type}")
                continue

            pattern = cls.CHAR_TYPES[char_type]
            if not re.search(pattern, password):
                missing_types.append(cls.CHAR_TYPE_NAMES.get(char_type, char_type))

        if missing_types:
            return False, f"密码必须包含：{', '.join(missing_types)}"

        # 3. 检查是否包含非法字符（只允许ASCII可打印字符）
        if not all(32 <= ord(char) <= 126 for char in password):
            return False, "密码包含非法字符，只允许使用ASCII可打印字符"

        return True, ""

    @classmethod
    def get_password_policy_description(cls) -> str:
        """
        获取密码策略描述文本

        Returns:
            str: 密码策略说明
        """
        config = cls.get_password_settings()
        min_length = config["min_length"]
        max_length = config["max_length"]
        required_types = config["required_char_types"]

        # 构建字符类型要求描述
        type_names = [cls.CHAR_TYPE_NAMES.get(t, t) for t in required_types if t in cls.CHAR_TYPE_NAMES]
        type_desc = f"必须包含：{', '.join(type_names)}" if type_names else "无特殊要求"

        return f"密码策略要求：\n" f"1. 长度为 {min_length}-{max_length} 个字符\n" f"2. {type_desc}\n" f"3. 特殊符号包括：!@#$%^&*()_+-=[]{{}};\\'\"\\|,.<>?/~`"
