# -- coding: utf-8 --
"""
显示字段冗余处理器

职责：
1. 为 organization/user/enum 类型字段生成 _display 冗余字段
2. 将原始ID数据转换为可搜索的字符串格式
3. 在实例创建/更新时自动维护冗余字段
4. 提供获取需要排除的原始字段列表的方法

冗余数据格式：
- organization: [1,2,3] → "技术部,运维组,北京分公司" (逗号分隔的字符串)
- user: "admin" → "超级管理员" (用户显示名)
- enum: "1" → "运行中" (枚举显示名)

命名规范：
- 原始字段: organization, created_by, status
- 冗余字段: organization_display, created_by_display, status_display
"""

from typing import  List

from apps.cmdb.constants.constants import MODEL
from apps.cmdb.display_field.constants import (
    DISPLAY_FIELD_TYPES,
    DISPLAY_SUFFIX,
    FIELD_TYPE_ORGANIZATION,
    FIELD_TYPE_USER,
    FIELD_TYPE_ENUM,
    DISPLAY_VALUES_SEPARATOR,
    USER_DISPLAY_FORMAT,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.logger import cmdb_logger as logger
from apps.system_mgmt.models import User, Group


class DisplayFieldConverter:
    """
    显示字段转换器 - 统一的字段值转换逻辑
    
    提供 organization/user/enum 三种类型的原始值到显示值的转换
    这是整个 CMDB 唯一的转换逻辑实现
    """
    
    @staticmethod
    def convert_organization(org_ids) -> str:
        """
        将组织ID列表转换为显示名称字符串
        
        Args:
            org_ids: 组织ID列表 [1, 2, 3] 或单个ID 1
        
        Returns:
            逗号分隔的组织名称字符串，如 "技术部, 运维组, 北京分公司"
        """
        if not org_ids:
            return ""
        
        # 确保是列表格式
        if not isinstance(org_ids, list):
            org_ids = [org_ids]
        
        groups = Group.objects.filter(id__in=org_ids).values_list('name', flat=True)
        if not groups:
            return ""
        return DISPLAY_VALUES_SEPARATOR.join(groups)
    
    @staticmethod
    def convert_user(user_list) -> str:
        """
        将用户ID列表转换为用户显示名称
        
        Args:
            user_list: 用户ID列表
        
        Returns:
            逗号分隔的用户名称，格式为 "display_name(username)"，如 "管理员(admin), 普通用户(user01)"
        """
        if not user_list:
            return ""
        
        users = User.objects.filter(id__in=user_list).values("username", "display_name")
        if not users:
            return ""
        
        # 格式化为 "display_name(username)" 格式
        formatted_users = []
        for user in users:
            username = user.get("username", "")
            display_name = user.get("display_name", "")
            
            # 如果 display_name 存在且不为空，使用 USER_DISPLAY_FORMAT 格式
            # 否则只使用 username
            if display_name and display_name.strip():
                formatted_users.append(USER_DISPLAY_FORMAT.format(
                    display_name=display_name,
                    username=username
                ))
            else:
                formatted_users.append(username)
        
        return DISPLAY_VALUES_SEPARATOR.join(formatted_users)
    
    @staticmethod
    def convert_enum(enum_id: str, options: List[dict]) -> str:
        """
        将枚举ID转换为枚举显示名称
        
        Args:
            enum_id: 枚举值ID
            options: 枚举选项列表 [{'id': '1', 'name': 'AA'}, {'id': '2', 'name': 'BB'}]
        
        Returns:
            枚举显示名称，如 "运行中"
        """
        if not enum_id:
            return ""
        
        if not options or not isinstance(options, list):
            logger.debug(f"[DisplayFieldConverter] 枚举选项为空，返回原始值: {enum_id}")
            return str(enum_id)
        
        # 查找匹配的枚举选项
        for option in options:
            option_id = option.get('id')
            option_name = option.get('name')
            
            if str(option_id) == str(enum_id):
                display_value = option_name or enum_id
                logger.debug(f"[DisplayFieldConverter] 枚举ID转换: {enum_id} → '{display_value}'")
                return display_value
        
        # 未找到匹配项，返回原始值
        logger.debug(f"[DisplayFieldConverter] 未找到枚举值 {enum_id}，使用原始值")
        return str(enum_id)


class DisplayFieldHandler:
    """
    显示字段冗余处理器
    
    负责将 organization/user/enum 类型的ID字段转换为可搜索的显示名称字段
    所有冗余字段统一转换为 str 类型，方便全文检索
    
    常量说明:
    - DISPLAY_FIELD_TYPES: 需要生成 _display 字段的类型 (从 constants 导入)
    - DISPLAY_SUFFIX: 冗余字段后缀 '_display' (从 constants 导入)
    """

    @classmethod
    def build_display_fields(cls, model_id: str, instance_data: dict, attrs: List[dict]) -> dict:
        """
        为实例数据构建冗余的 _display 字段
        
        工作流程：
        1. 遍历模型的所有字段定义
        2. 对于 organization/user/enum 类型的字段，生成对应的 _display 字段
        3. 将原始ID转换为显示名称（统一转为 str 类型）
        
        Args:
            model_id: 模型ID
            instance_data: 实例数据（会被直接修改，添加 _display 字段）
            attrs: 模型字段定义列表 [{'attr_id': 'status', 'attr_type': 'enum', 'option': [...]}]
        
        Returns:
            包含 _display 字段的实例数据（同一个对象引用）
        
        Example:
            输入: {
                'inst_name': '服务器01',
                'organization': [1, 2, 3],
                'created_by': 'admin',
                'status': '1'
            }
            输出: {
                'inst_name': '服务器01',
                'organization': [1, 2, 3],
                'organization_display': '技术部,运维组,北京分公司',  # 新增
                'created_by': 'admin',
                'created_by_display': '超级管理员',  # 新增
                'status': '1',
                'status_display': '运行中'  # 新增
            }
        """
        logger.debug(f"[DisplayFieldHandler] 开始构建 _display 字段, 模型: {model_id}")

        if not attrs:
            logger.warning(f"[DisplayFieldHandler] 模型 {model_id} 没有字段定义，跳过")
            return instance_data

        # 遍历所有字段定义
        for attr in attrs:
            attr_id = attr.get('attr_id')
            attr_type = attr.get('attr_type')

            # 跳过非目标类型的字段
            if attr_type not in DISPLAY_FIELD_TYPES:
                continue

            # 跳过实例中不存在的字段
            if attr_id not in instance_data:
                logger.debug(f"[DisplayFieldHandler] 字段 {attr_id} 在实例中不存在，跳过")
                continue

            # 获取原始值
            original_value = instance_data[attr_id]
            display_field_name = f"{attr_id}{DISPLAY_SUFFIX}"

            try:
                # 根据类型转换为显示名称（使用统一的转换器）
                if attr_type == FIELD_TYPE_ORGANIZATION:
                    display_value = DisplayFieldConverter.convert_organization(original_value)
                elif attr_type == FIELD_TYPE_USER:
                    display_value = DisplayFieldConverter.convert_user(original_value)
                elif attr_type == FIELD_TYPE_ENUM:
                    display_value = DisplayFieldConverter.convert_enum(
                        original_value,
                        attr.get('option', [])
                    )
                else:
                    logger.warning(f"[DisplayFieldHandler] 未知字段类型: {attr_type}")
                    continue

                # 存储冗余字段
                instance_data[display_field_name] = display_value

                logger.debug(
                    f"[DisplayFieldHandler] 生成冗余字段: {display_field_name} = '{display_value}' "
                    f"(原始值: {original_value}, 类型: {attr_type})"
                )

            except Exception as e:
                logger.error(
                    f"[DisplayFieldHandler] 生成 _display 字段失败: "
                    f"字段={attr_id}, 类型={attr_type}, 原始值={original_value}, 错误={e}",
                    exc_info=True
                )
                # 失败时使用原始值的字符串表示作为降级方案
                instance_data[display_field_name] = str(original_value)

        logger.info(
            f"[DisplayFieldHandler] _display 字段构建完成, 模型: {model_id}, "
            f"新增字段数: {sum(1 for k in instance_data.keys() if k.endswith(DISPLAY_SUFFIX))}"
        )

        return instance_data

    @classmethod
    def remove_display_fields(cls, instance_data: dict) -> dict:
        """
        移除实例数据中的所有 _display 冗余字段
        
        用于数据导出、API响应等不需要冗余字段的场景
        
        Args:
            instance_data: 实例数据
        
        Returns:
            移除 _display 字段后的实例数据（会修改原对象）
        """
        display_fields = [key for key in instance_data.keys() if key.endswith(DISPLAY_SUFFIX)]

        for field in display_fields:
            del instance_data[field]

        logger.debug(f"[DisplayFieldHandler] 移除了 {len(display_fields)} 个 _display 字段")

        return instance_data

    @classmethod
    def get_exclude_fields_from_attrs(cls, attrs: List[dict]) -> List[str]:
        """
        从模型字段定义中提取需要排除的原始字段列表
        
        用于全文检索时构建排除条件，只搜索 _display 字段，不搜索原始ID字段
        
        Args:
            attrs: 模型字段定义列表
        
        Returns:
            需要排除的字段名列表，如 ['organization', 'created_by', 'status']
        
        Example:
            输入: [
                {'attr_id': 'inst_name', 'attr_type': 'str'},
                {'attr_id': 'organization', 'attr_type': 'organization'},
                {'attr_id': 'status', 'attr_type': 'enum'}
            ]
            输出: ['organization', 'status']
        """
        exclude_fields = []

        for attr in attrs:
            attr_id = attr.get('attr_id')
            attr_type = attr.get('attr_type')

            if attr_type in DISPLAY_FIELD_TYPES:
                exclude_fields.append(attr_id)

        logger.debug(
            f"[DisplayFieldHandler] 提取排除字段完成, "
            f"字段数: {len(exclude_fields)}, 字段列表: {exclude_fields}"
        )

        return exclude_fields

    @staticmethod
    def _convert_organization_to_display(org_ids) -> str:
        """委托给 DisplayFieldConverter（保持向后兼容）"""
        return DisplayFieldConverter.convert_organization(org_ids)

    @staticmethod
    def _convert_user_to_display(user_list: str) -> str:
        """委托给 DisplayFieldConverter（保持向后兼容）"""
        return DisplayFieldConverter.convert_user(user_list)

    @staticmethod
    def _convert_enum_to_display(enum_id: str, options: List[dict]) -> str:
        """委托给 DisplayFieldConverter（保持向后兼容）"""
        return DisplayFieldConverter.convert_enum(enum_id, options)

    @classmethod
    def get_all_exclude_fields(cls) -> List[str]:
        """
        获取所有模型中需要排除的原始字段列表（用于全文检索）
        
        工作流程：
        1. 查询所有模型定义
        2. 提取每个模型中 organization/user/enum 类型的字段
        3. 合并去重后返回
        
        Returns:
            所有需要排除的字段名列表（跨所有模型）
            
        注意：
            - 这个方法会查询数据库，建议在应用启动时调用并缓存结果
            - 适合用于初始化全文检索的排除字段列表
        """
        logger.info("[DisplayFieldHandler] 开始获取所有模型的排除字段...")

        try:

            # 查询所有模型
            with GraphClient() as ag:
                models, _ = ag.query_entity(MODEL, [])

            # 收集所有需要排除的字段
            all_exclude_fields = set()

            for model in models:
                model_id = model.get('model_id')
                attrs_json = model.get('attrs', '[]')

                try:
                    # 延迟导入避免循环依赖
                    from apps.cmdb.services.model import ModelManage
                    attrs = ModelManage.parse_attrs(attrs_json)
                    exclude_fields = cls.get_exclude_fields_from_attrs(attrs)
                    all_exclude_fields.update(exclude_fields)
                except Exception as e:
                    logger.warning(
                        f"[DisplayFieldHandler] 解析模型 {model_id} 字段失败: {e}"
                    )
                    continue

            result = sorted(list(all_exclude_fields))

            logger.info(
                f"[DisplayFieldHandler] 获取排除字段完成, "
                f"模型数: {len(models)}, 排除字段数: {len(result)}, "
                f"字段列表: {result}"
            )

            return result

        except Exception as e:
            logger.error(
                f"[DisplayFieldHandler] 获取所有排除字段失败: {e}",
                exc_info=True
            )
            return []


# 便捷别名
display_field_handler = DisplayFieldHandler()
