# -- coding: utf-8 --
"""
显示字段初始化器

职责：
1. 为现有模型批量添加 _display 字段定义
2. 为现有实例批量生成 _display 字段值
3. 支持三种字段类型：organization/user/enum

数据源：
- organization: apps.system_mgmt.models.user.Group（组织表）
- user: apps.system_mgmt.models.user.User（用户表）
- enum: 模型字段定义中的 option 字段

使用场景：
- 项目数据迁移（一次性初始化所有历史数据）
- 通过 management 命令调用
"""
import json
from typing import Dict, List
from apps.core.logger import cmdb_logger as logger
from apps.cmdb.constants.constants import DISPLAY_FIELD_CONFIG
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
from apps.cmdb.constants.constants import MODEL, INSTANCE


class DisplayFieldInitializer:
    """
    显示字段初始化器
    
    用于历史数据迁移，批量为模型和实例添加 _display 字段
    
    常量说明:
    - TARGET_FIELD_TYPES: 需要处理的字段类型 (从 constants 导入)
    - DISPLAY_SUFFIX: 冗余字段后缀 '_display' (从 constants 导入)
    """

    def __init__(self):
        """初始化映射缓存"""
        self._org_map: Dict[int, str] = {}  # {org_id: org_name}
        self._user_map: Dict[int, Dict[str, str]] = {}  # {user_id: {'username': 'admin', 'display_name': '管理员'}}
        self._enum_map: Dict[str, str] = {}  # {"model_id.attr_id.enum_id": enum_name}

    def initialize_all(self) -> dict:
        """
        初始化所有模型和实例的 _display 字段
        
        工作流程：
        1. 预加载组织和用户映射数据（避免重复查询）
        2. 查询所有模型
        3. 为每个模型添加 _display 字段定义
        4. 为每个模型的所有实例添加 _display 字段值
        
        Returns:
            执行结果统计 {
                'success': True/False,
                'models_processed': 10,
                'instances_processed': 1234,
                'errors': []
            }
        """
        logger.info("[DisplayFieldInitializer] 开始初始化 _display 字段...")

        result = {
            'success': True,
            'models_processed': 0,
            'instances_processed': 0,
            'errors': []
        }

        try:
            # 1. 查询所有模型(用于预加载枚举映射)
            models = self._get_all_models()

            # 2. 预加载映射数据(organization/user/enum)
            self._preload_mappings(models)

            # 3. 逐个处理模型
            for model in models:
                model_id = model.get('model_id')

                try:
                    # 3.1 为模型添加 _display 字段定义
                    attrs = self._add_display_fields_to_model(model)

                    # 3.2 为实例添加 _display 字段值
                    instance_count = self._add_display_fields_to_instances(
                        model_id,
                        attrs
                    )

                    result['models_processed'] += 1
                    result['instances_processed'] += instance_count

                    logger.info(
                        f"[DisplayFieldInitializer] 模型处理完成: {model_id}, "
                        f"实例数: {instance_count}"
                    )

                except Exception as e:
                    error_msg = f"处理模型 {model_id} 失败: {e}"
                    logger.error(f"[DisplayFieldInitializer] {error_msg}", exc_info=True)
                    result['errors'].append(error_msg)
                    result['success'] = False

            logger.info(
                f"[DisplayFieldInitializer] 初始化完成！\n"
                f"  - 模型数: {result['models_processed']}\n"
                f"  - 实例数: {result['instances_processed']}\n"
                f"  - 错误数: {len(result['errors'])}"
            )

            return result

        except Exception as e:
            error_msg = f"初始化异常: {e}"
            logger.error(f"[DisplayFieldInitializer] {error_msg}", exc_info=True)
            result['success'] = False
            result['errors'].append(error_msg)
            return result

    def _preload_mappings(self, models: List[dict]):
        """
        预加载组织、用户和枚举映射数据
        
        避免在处理每个实例时重复查询数据库
        
        Args:
            models: 所有模型列表(用于提取枚举映射)
        """

        # 1. 加载组织映射
        try:
            from apps.system_mgmt.models.user import Group

            groups = Group.objects.all()
            self._org_map = {group.id: group.name for group in groups}
        except Exception as e:
            logger.error(f"[DisplayFieldInitializer] 加载组织映射失败: {e}", exc_info=True)
            self._org_map = {}

        # 2. 加载用户映射
        try:
            from apps.system_mgmt.models.user import User

            users = User.objects.all()
            # 存储完整的用户信息（username 和 display_name）
            for user in users:
                self._user_map[user.id] = {
                    'username': user.username,
                    'display_name': user.display_name
                }

        except Exception as e:
            logger.error(f"[DisplayFieldInitializer] 加载用户映射失败: {e}", exc_info=True)
            self._user_map = {}

        # 3. 加载枚举映射(从所有模型的 attrs 中提取)
        try:

            enum_count = 0
            for model in models:
                model_id = model.get('model_id')
                attrs_json = model.get('attrs', '[]')

                try:
                    # 延迟导入避免循环依赖
                    from apps.cmdb.services.model import ModelManage
                    attrs = ModelManage.parse_attrs(attrs_json)

                    # 遍历字段,提取枚举选项
                    for attr in attrs:
                        attr_id = attr.get('attr_id')
                        attr_type = attr.get('attr_type')

                        if attr_type == 'enum':
                            options = attr.get('option', [])

                            # 为每个枚举选项建立映射
                            for option in options:
                                option_id = option.get('id')
                                option_name = option.get('name')

                                if option_id and option_name:
                                    # 映射key格式: "model_id.attr_id.enum_id"
                                    map_key = f"{model_id}.{attr_id}.{option_id}"
                                    self._enum_map[map_key] = option_name
                                    enum_count += 1

                except Exception as e:
                    logger.warning(
                        f"[DisplayFieldInitializer] 解析模型 {model_id} 枚举映射失败: {e}"
                    )
                    continue

            logger.info(
                f"[DisplayFieldInitializer] 枚举映射加载完成, 数量: {enum_count}"
            )

        except Exception as e:
            logger.error(f"[DisplayFieldInitializer] 加载枚举映射失败: {e}", exc_info=True)
            self._enum_map = {}

    def _get_all_models(self) -> List[dict]:
        """
        查询所有模型
        
        Returns:
            模型列表
        """

        with GraphClient() as ag:
            models, _ = ag.query_entity(MODEL, [])

        return models

    def _add_display_fields_to_model(self, model: dict) -> List[dict]:
        """
        为模型添加 _display 字段定义
        
        工作流程：
        1. 解析模型的 attrs 字段
        2. 查找 organization/user/enum 类型的字段
        3. 为每个匹配字段添加对应的 _display 字段定义
        4. 更新模型的 attrs
        
        Args:
            model: 模型数据
        
        Returns:
            更新后的 attrs 列表
        """

        model_id = model.get('model_id')
        attrs_json = model.get('attrs', '[]')

        # 解析 attrs
        try:
            # 延迟导入避免循环依赖
            from apps.cmdb.services.model import ModelManage
            attrs = ModelManage.parse_attrs(attrs_json)
        except Exception as e:
            logger.error(f"[DisplayFieldInitializer] 解析模型 {model_id} attrs 失败: {e}")
            return []

        # 检查是否需要添加 _display 字段
        original_attr_count = len(attrs)
        display_fields_to_add = []

        for attr in attrs:
            attr_id = attr.get('attr_id')
            attr_type = attr.get('attr_type')

            # 跳过非目标类型
            if attr_type not in DISPLAY_FIELD_TYPES:
                continue

            # 检查是否已存在 _display 字段
            display_field_id = f"{attr_id}{DISPLAY_SUFFIX}"
            if any(a.get('attr_id') == display_field_id for a in attrs):
                logger.debug(
                    f"[DisplayFieldInitializer] 模型 {model_id} 字段 {display_field_id} 已存在，跳过"
                )
                continue

            # 构建 _display 字段定义（使用统一的配置常量）
            display_field = {
                'attr_id': display_field_id,
                'attr_name': attr.get('attr_name'),
                'attr_group': attr.get('attr_group', 'default'),
                'group_id': attr.get('group_id'),
                'model_id': model_id,
                **DISPLAY_FIELD_CONFIG  # 应用统一的冗余字段配置
            }

            display_fields_to_add.append(display_field)

        # 如果没有需要添加的字段，直接返回
        if not display_fields_to_add:
            logger.debug(f"[DisplayFieldInitializer] 模型 {model_id} 无需添加 _display 字段")
            return attrs

        # 添加 _display 字段到 attrs
        attrs.extend(display_fields_to_add)

        # 更新模型
        try:
            new_attrs_json = json.dumps(attrs, ensure_ascii=False)
            model_internal_id = model.get('_id')

            with GraphClient() as ag:
                ag.set_entity_properties(
                    MODEL,
                    [model_internal_id],
                    {'attrs': new_attrs_json},
                    {},
                    [],
                    False
                )

            logger.info(
                f"[DisplayFieldInitializer] 模型 {model_id} 添加 _display 字段完成, "
                f"原字段数: {original_attr_count}, "
                f"新增字段数: {len(display_fields_to_add)}, "
                f"新增字段: {[f['attr_id'] for f in display_fields_to_add]}"
            )

        except Exception as e:
            logger.error(
                f"[DisplayFieldInitializer] 更新模型 {model_id} attrs 失败: {e}",
                exc_info=True
            )
            raise

        return attrs

    def _add_display_fields_to_instances(self, model_id: str, attrs: List[dict]) -> int:
        """
        为模型的所有实例添加 _display 字段值
        
        工作流程：
        1. 查询模型的所有实例
        2. 为每个实例生成 _display 字段值
        3. 批量更新实例
        
        Args:
            model_id: 模型ID
            attrs: 模型字段定义列表
        
        Returns:
            处理的实例数量
        """

        # 1. 查询所有实例
        try:
            with GraphClient() as ag:
                instances, _ = ag.query_entity(label=INSTANCE,
                                               params=[{"field": "model_id", "type": "str=", "value": model_id}],
                                               )

            if not instances:
                logger.debug(f"[DisplayFieldInitializer] 模型 {model_id} 没有实例")
                return 0

            logger.info(
                f"[DisplayFieldInitializer] 模型 {model_id} 查询到 {len(instances)} 个实例"
            )

        except Exception as e:
            logger.error(
                f"[DisplayFieldInitializer] 查询模型 {model_id} 实例失败: {e}",
                exc_info=True
            )
            return 0

        # 2. 批量处理实例
        processed_count = 0

        for instance in instances:
            try:
                # 生成 _display 字段
                display_fields = self._build_display_fields_for_instance(
                    instance,
                    attrs,
                    model_id
                )

                # 如果没有需要更新的字段，跳过
                if not display_fields:
                    continue

                instance.update(display_fields)

                # 更新实例
                inst_id = instance.get('inst_id')
                instance_internal_id = instance.get('_id')

                with GraphClient() as ag:
                    new_instance = ag.set_entity_properties(
                        INSTANCE,
                        [instance_internal_id],
                        instance,
                        {},
                        [],
                        False
                    )
                    logger.debug("修改后实例数据: {}".format(new_instance))

                processed_count += 1

                logger.debug(
                    f"[DisplayFieldInitializer] 实例 {inst_id} 更新完成, "
                    f"字段: {list(display_fields.keys())}"
                )

            except Exception as e:
                logger.error(
                    f"[DisplayFieldInitializer] 更新实例 {instance.get('inst_id')} 失败: {e}",
                    exc_info=True
                )
                continue

        logger.info(
            f"[DisplayFieldInitializer] 模型 {model_id} 实例处理完成, "
            f"总数: {len(instances)}, 更新数: {processed_count}"
        )

        return processed_count

    def _build_display_fields_for_instance(
            self,
            instance: dict,
            attrs: List[dict],
            model_id: str
    ) -> Dict[str, str]:
        """
        为单个实例构建 _display 字段
        
        Args:
            instance: 实例数据
            attrs: 模型字段定义
            model_id: 模型ID(用于枚举映射查询)
        
        Returns:
            _display 字段字典，如 {'organization_display': '技术部,运维组'}
        """
        display_fields = {}

        for attr in attrs:
            attr_id = attr.get('attr_id')
            attr_type = attr.get('attr_type')

            # 跳过非目标类型
            if attr_type not in DISPLAY_FIELD_TYPES:
                continue

            # 跳过实例中不存在的字段
            if attr_id not in instance:
                continue

            # 获取原始值
            original_value = instance[attr_id]
            display_field_name = f"{attr_id}{DISPLAY_SUFFIX}"

            # 根据类型转换
            try:
                if attr_type == FIELD_TYPE_ORGANIZATION:
                    display_value = self._convert_organization(original_value)
                elif attr_type == FIELD_TYPE_USER:
                    display_value = self._convert_user(original_value)
                elif attr_type == FIELD_TYPE_ENUM:
                    display_value = self._convert_enum(
                        model_id,
                        attr_id,
                        original_value
                    )
                else:
                    continue

                display_fields[display_field_name] = display_value

            except Exception as e:
                logger.warning(
                    f"[DisplayFieldInitializer] 转换字段 {attr_id} 失败: {e}, "
                    f"使用原始值"
                )
                display_fields[display_field_name] = str(original_value)

        return display_fields

    def _convert_organization(self, org_ids) -> str:
        """
        将组织ID列表转换为显示名称
        
        Args:
            org_ids: 组织ID列表或单个ID
        
        Returns:
            逗号分隔的组织名称字符串
        """
        if not org_ids:
            return ""

        # 确保是列表
        if not isinstance(org_ids, list):
            org_ids = [org_ids]

        # 转换为名称
        org_names = []
        for org_id in org_ids:
            # 从预加载的映射中查询
            org_name = self._org_map.get(org_id, str(org_id))
            org_names.append(org_name)

        return DISPLAY_VALUES_SEPARATOR.join(org_names)

    def _convert_user(self, user_list: List[int]) -> str:
        """
        将用户ID转换为用户显示名称
        
        Args:
            user_list: 用户ID列表
        
        Returns:
            逗号分隔的用户名称，格式为 "display_name(username)"，如 "管理员(admin), 普通用户(user01)"
        """
        if not user_list:
            return ""

        # 从预加载的映射中查询并格式化为 "display_name(username)" 格式
        formatted_users = []
        for user_id in user_list:
            user_info = self._user_map.get(user_id)

            if user_info:
                username = user_info.get('username', '')
                display_name = user_info.get('display_name', '')

                # 如果 display_name 存在且不为空，使用 USER_DISPLAY_FORMAT 格式
                # 否则只使用 username
                if display_name and display_name.strip():
                    formatted_users.append(USER_DISPLAY_FORMAT.format(
                        display_name=display_name,
                        username=username
                    ))
                else:
                    formatted_users.append(username)
            else:
                # 如果映射中找不到，使用原始ID
                formatted_users.append(str(user_id))

        return DISPLAY_VALUES_SEPARATOR.join(formatted_users)

    def _convert_enum(self, model_id: str, attr_id: str, enum_id: str) -> str:
        """
        将枚举ID转换为枚举名称(从预加载的映射中查询)
        
        Args:
            model_id: 模型ID
            attr_id: 字段ID
            enum_id: 枚举ID
        
        Returns:
            枚举名称
        """
        if not enum_id:
            return ""

        # 构建映射key: "model_id.attr_id.enum_id"
        map_key = f"{model_id}.{attr_id}.{enum_id}"

        # 从预加载的映射中查询
        enum_name = self._enum_map.get(map_key)

        if enum_name:
            return enum_name

        # 降级方案:返回原始ID
        logger.debug(
            f"[DisplayFieldInitializer] 未找到枚举映射: {map_key}，使用原始值"
        )
        return str(enum_id)


# 便捷别名
display_field_initializer = DisplayFieldInitializer()
