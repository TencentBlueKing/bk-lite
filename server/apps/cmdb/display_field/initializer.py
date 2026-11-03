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
from collections import defaultdict
from typing import Dict, List, Union

from apps.cmdb.constants.constants import DISPLAY_FIELD_CONFIG, INSTANCE, MODEL
from apps.cmdb.display_field.constants import (
    DISPLAY_FIELD_TYPES,
    DISPLAY_SUFFIX,
    DISPLAY_VALUES_SEPARATOR,
    FIELD_TYPE_ENUM,
    FIELD_TYPE_ORGANIZATION,
    FIELD_TYPE_TAG,
    FIELD_TYPE_USER,
    USER_DISPLAY_FORMAT,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.graph.validators import MAX_BATCH_UPDATE_PROPERTY_VALUES
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info


class _DisplayFieldQueryError(Exception):
    """实例查询失败。原始 traceback 只留在查询处的日志里。"""

    def __init__(self, model_id: str):
        self.model_id = model_id
        super().__init__(model_id)


class _DisplayFieldInstanceUpdateError(Exception):
    """同一模型有实例写入失败。errors 只收一条摘要。"""

    def __init__(self, inst_id, failure_count: int, instances_processed: int):
        self.inst_id = inst_id
        self.failure_count = failure_count
        self.instances_processed = instances_processed
        super().__init__(str(failure_count))


class DisplayFieldInitializer:
    """
    显示字段初始化器

    用于历史数据迁移，批量为模型和实例添加 _display 字段

    常量说明:
    - TARGET_FIELD_TYPES: 需要处理的字段类型 (从 constants 导入)
    - DISPLAY_SUFFIX: 冗余字段后缀 '_display' (从 constants 导入)
    """

    INSTANCE_PAGE_SIZE = 500
    _INSTANCE_DISPLAY_TYPES = frozenset(
        {
            FIELD_TYPE_ORGANIZATION,
            FIELD_TYPE_USER,
            FIELD_TYPE_ENUM,
            FIELD_TYPE_TAG,
        }
    )

    def __init__(self):
        """初始化映射缓存"""
        self._org_map: Dict[int, str] = {}  # {org_id: org_name}
        self._user_map: Dict[int, Dict[str, str]] = {}  # {user_id: {'username': 'admin', 'display_name': '管理员'}}
        self._enum_map: Dict[str, str] = {}  # {"model_id.attr_id.enum_id": enum_name}

    def initialize_all(self, *, instances: bool = True) -> dict:
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
            "success": True,
            "models_processed": 0,
            "instances_processed": 0,
            "errors": [],
        }

        try:
            # 1. 查询所有模型(用于预加载枚举映射)
            models = self._get_all_models()

            # 2. 预加载映射数据(organization/user/enum)
            self._preload_mappings(models)

            # 3. 逐个处理模型
            for model in models:
                model_id = model.get("model_id")

                try:
                    # 3.1 为模型添加 _display 字段定义
                    attrs = self._add_display_fields_to_model(model)

                    # 3.2 为实例添加 _display 字段值。启动期只补模型定义，实例回填走运行期任务。
                    instance_count = self._add_display_fields_to_instances(model_id, attrs) if instances else 0

                    result["models_processed"] += 1
                    result["instances_processed"] += instance_count

                    logger.info(f"[DisplayFieldInitializer] 模型处理完成: {model_id}, " f"实例数: {instance_count}")

                except _DisplayFieldQueryError:
                    result["errors"].append(f"查询实例失败，model_id={model_id}")
                    result["success"] = False
                except _DisplayFieldInstanceUpdateError as exc:
                    result["instances_processed"] += exc.instances_processed
                    result["errors"].append(f"更新实例失败，model_id={model_id}，inst_id={exc.inst_id}，失败{exc.failure_count}次")
                    result["success"] = False
                except Exception as e:
                    error_msg = f"处理模型 {model_id} 失败: {e}"
                    logger.error(f"[DisplayFieldInitializer] {error_msg}", exc_info=True)
                    result["errors"].append(error_msg)
                    result["success"] = False

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
            result["success"] = False
            result["errors"].append(error_msg)
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
                    "username": user.username,
                    "display_name": user.display_name,
                }

        except Exception as e:
            logger.error(f"[DisplayFieldInitializer] 加载用户映射失败: {e}", exc_info=True)
            self._user_map = {}

        # 3. 加载枚举映射(从所有模型的 attrs 中提取)
        try:
            enum_count = 0
            for model in models:
                model_id = model.get("model_id")
                attrs_json = model.get("attrs", "[]")

                try:
                    # 延迟导入避免循环依赖
                    from apps.cmdb.services.model import ModelManage

                    attrs = ModelManage.parse_attrs(attrs_json)

                    # 遍历字段,提取枚举选项
                    for attr in attrs:
                        attr_id = attr.get("attr_id")
                        attr_type = attr.get("attr_type")

                        if attr_type == "enum":
                            options = attr.get("option", [])

                            # 为每个枚举选项建立映射
                            for option in options:
                                option_id = option.get("id")
                                option_name = option.get("name")

                                if option_id and option_name:
                                    # 映射key格式: "model_id.attr_id.enum_id"
                                    map_key = f"{model_id}.{attr_id}.{option_id}"
                                    self._enum_map[map_key] = option_name
                                    enum_count += 1

                except Exception as e:
                    logger.warning(f"[DisplayFieldInitializer] 解析模型 {model_id} 枚举映射失败: {e}")
                    continue

            logger.info(f"[DisplayFieldInitializer] 枚举映射加载完成, 数量: {enum_count}")

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

        model_id = model.get("model_id")
        attrs_json = model.get("attrs", "[]")

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
            attr_id = attr.get("attr_id")
            attr_type = attr.get("attr_type")

            # 跳过非目标类型
            if attr_type not in DISPLAY_FIELD_TYPES:
                continue

            # 检查是否已存在 _display 字段
            display_field_id = f"{attr_id}{DISPLAY_SUFFIX}"
            if any(a.get("attr_id") == display_field_id for a in attrs):
                logger.debug(f"[DisplayFieldInitializer] 模型 {model_id} 字段 {display_field_id} 已存在，跳过")
                continue

            # 构建 _display 字段定义（使用统一的配置常量）
            display_field = {
                "attr_id": display_field_id,
                "attr_name": attr.get("attr_name"),
                "attr_group": attr.get("attr_group", "default"),
                "group_id": attr.get("group_id"),
                "model_id": model_id,
                **DISPLAY_FIELD_CONFIG,  # 应用统一的冗余字段配置
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
            model_internal_id = model.get("_id")

            with GraphClient() as ag:
                ag.set_entity_properties(MODEL, [model_internal_id], {"attrs": new_attrs_json}, {}, [], False)

            from apps.cmdb.display_field.cache import ExcludeFieldsCache

            ExcludeFieldsCache.invalidate_model_attrs(model_id)

            logger.info(
                f"[DisplayFieldInitializer] 模型 {model_id} 添加 _display 字段完成, "
                f"原字段数: {original_attr_count}, "
                f"新增字段数: {len(display_fields_to_add)}, "
                f"新增字段: {[f['attr_id'] for f in display_fields_to_add]}"
            )

        except Exception as e:
            logger.error(
                f"[DisplayFieldInitializer] 更新模型 {model_id} attrs 失败: {e}",
                exc_info=True,
            )
            raise

        return attrs

    def backfill_bounded(self, *, max_instances: int, cursor: dict | None) -> dict:
        """按模型分页回填，单次最多扫描 max_instances 个实例节点。

        已有且相同的 _display 不写。查询失败停在当前游标，交给下一次运行重试。
        """
        models = self._get_all_models()
        self._preload_mappings(models)
        prepared = []
        for model in models:
            model_id = model.get("model_id")
            attrs = self._parse_model_attrs(model)
            if model_id and self._has_instance_display_fields(attrs):
                prepared.append((model_id, attrs))

        start_index = 0
        last_id = None
        if cursor and cursor.get("model_id"):
            model_ids = [item[0] for item in prepared]
            if cursor["model_id"] in model_ids:
                start_index = model_ids.index(cursor["model_id"])
                last_id = cursor.get("last_id")

        seen = 0
        updated = 0
        errors = []

        def _progress(done: bool, query_failed: bool, next_cursor):
            return {
                "done": done,
                "query_failed": query_failed,
                "next_cursor": next_cursor,
                "instances_seen": seen,
                "instances_updated": updated,
                "errors": errors,
            }

        with GraphClient() as ag:
            for index in range(start_index, len(prepared)):
                model_id, attrs = prepared[index]
                page_after = last_id if index == start_index else None
                while seen < max_instances:
                    try:
                        instances = self._query_instance_page(ag, model_id, page_after)
                    except Exception as exc:
                        self._log_query_failure(model_id, exc)
                        errors.append(f"查询实例失败，model_id={model_id}")
                        return _progress(False, True, {"model_id": model_id, "last_id": page_after})
                    if not instances:
                        break
                    page_updated, failure_count, first_inst_id, first_exc = self._apply_instance_page(ag, model_id, attrs, instances)
                    updated += page_updated
                    if failure_count:
                        self._log_write_failure(model_id, first_exc, failure_count)
                        errors.append(f"更新实例失败，model_id={model_id}，inst_id={first_inst_id}，失败{failure_count}次")
                    seen += len(instances)
                    next_id = instances[-1].get("_id")
                    if page_after is not None and next_id == page_after:
                        errors.append(f"查询实例失败，model_id={model_id}")
                        return _progress(False, True, {"model_id": model_id, "last_id": page_after})
                    page_after = next_id
                    model_finished = len(instances) < self.INSTANCE_PAGE_SIZE
                    if seen >= max_instances:
                        if model_finished:
                            if index + 1 >= len(prepared):
                                return _progress(True, False, None)
                            next_model_id = prepared[index + 1][0]
                            return _progress(False, False, {"model_id": next_model_id, "last_id": None})
                        return _progress(False, False, {"model_id": model_id, "last_id": page_after})
                    if model_finished:
                        break
        return _progress(True, False, None)

    def _add_display_fields_to_instances(self, model_id: str, attrs: List[dict]) -> int:
        """分页回填一个模型的实例。值未变化的实例不写图。"""
        if not self._has_instance_display_fields(attrs):
            return 0

        processed_count = 0
        failure_count = 0
        first_failed_inst_id = None
        first_exc = None
        last_id = None
        scanned = 0

        with GraphClient() as ag:
            while True:
                try:
                    instances = self._query_instance_page(ag, model_id, last_id)
                except Exception as exc:
                    self._log_query_failure(model_id, exc)
                    raise _DisplayFieldQueryError(model_id) from None

                if not instances:
                    break

                page_updated, page_failures, page_inst_id, page_exc = self._apply_instance_page(ag, model_id, attrs, instances)
                processed_count += page_updated
                if page_failures:
                    failure_count += page_failures
                    if first_failed_inst_id is None:
                        first_failed_inst_id = page_inst_id
                        first_exc = page_exc
                scanned += len(instances)
                next_id = instances[-1].get("_id")
                if last_id is not None and next_id == last_id:
                    self._log_query_failure(model_id, RuntimeError("cursor_not_advanced"))
                    raise _DisplayFieldQueryError(model_id) from None
                last_id = next_id
                if len(instances) < self.INSTANCE_PAGE_SIZE:
                    break

        if failure_count:
            self._log_write_failure(model_id, first_exc or RuntimeError("write_failed"), failure_count)
            raise _DisplayFieldInstanceUpdateError(
                inst_id=first_failed_inst_id,
                failure_count=failure_count,
                instances_processed=processed_count,
            )

        logger.info(
            "[DisplayFieldInitializer] event=display_backfill_model_finished model_id=%s scanned=%s updated=%s",
            model_id,
            scanned,
            processed_count,
        )
        return processed_count

    @classmethod
    def _has_instance_display_fields(cls, attrs: List[dict]) -> bool:
        return any(attr.get("attr_type") in cls._INSTANCE_DISPLAY_TYPES for attr in attrs)

    @staticmethod
    def _parse_model_attrs(model: dict) -> List[dict]:
        try:
            from apps.cmdb.services.model import ModelManage

            return ModelManage.parse_attrs(model.get("attrs", "[]"))
        except Exception as exc:
            logger.warning(
                "[DisplayFieldInitializer] event=display_backfill_attrs_skipped model_id=%s error_type=%s",
                model.get("model_id"),
                type(exc).__name__,
            )
            return []

    def _query_instance_page(self, ag, model_id: str, last_id):
        params = [{"field": "model_id", "type": "str=", "value": model_id}]
        if last_id is not None:
            params.append({"field": "id", "type": "id>", "value": last_id})
        instances, _ = ag.query_entity(
            label=INSTANCE,
            params=params,
            page={"skip": 0, "limit": self.INSTANCE_PAGE_SIZE},
            include_count=False,
        )
        return instances or []

    def _apply_instance_page(self, ag, model_id: str, attrs: List[dict], instances: List[dict]):
        grouped = defaultdict(list)
        expected = {}
        inst_ids = {}
        failure_count = 0
        first_inst_id = None
        first_exc = None

        for instance in instances:
            display_fields = self._build_display_fields_for_instance(instance, attrs, model_id)
            changed = {field: value for field, value in display_fields.items() if instance.get(field) != value}
            if not changed:
                continue
            internal_id = instance.get("_id")
            inst_id = instance.get("inst_id")
            if internal_id is None:
                failure_count += 1
                if first_inst_id is None:
                    first_inst_id = inst_id
                    first_exc = RuntimeError("missing_internal_id")
                continue
            expected[internal_id] = len(changed)
            inst_ids[internal_id] = inst_id
            for field, value in changed.items():
                grouped[field].append({"id": internal_id, "value": value})

        written = defaultdict(int)
        failed_ids = set()

        def _mark_failed(internal_id, exc):
            nonlocal failure_count, first_inst_id, first_exc
            if internal_id in failed_ids:
                return
            failed_ids.add(internal_id)
            failure_count += 1
            if first_inst_id is None:
                first_inst_id = inst_ids.get(internal_id)
                first_exc = exc

        for field, rows in grouped.items():
            for offset in range(0, len(rows), MAX_BATCH_UPDATE_PROPERTY_VALUES):
                chunk = rows[offset : offset + MAX_BATCH_UPDATE_PROPERTY_VALUES]
                payload = [{"id": row["id"], "value": row["value"]} for row in chunk]
                try:
                    ag.batch_update_node_property_values(INSTANCE, field, payload)
                except Exception:
                    for row in chunk:
                        try:
                            ag.batch_update_node_property_values(INSTANCE, field, [{"id": row["id"], "value": row["value"]}])
                        except Exception as row_exc:
                            _mark_failed(row["id"], row_exc)
                        else:
                            written[row["id"]] += 1
                else:
                    for row in chunk:
                        written[row["id"]] += 1

        updated = sum(1 for internal_id, count in expected.items() if written[internal_id] == count and internal_id not in failed_ids)
        return updated, failure_count, first_inst_id, first_exc

    @staticmethod
    def _log_query_failure(model_id: str, exc: Exception) -> None:
        logger.error(
            "[DisplayFieldInitializer] event=display_backfill_query_failed model_id=%s failed_stage=query_instance error_type=%s",
            model_id,
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )

    @staticmethod
    def _log_write_failure(model_id: str, exc: Exception, failure_count: int) -> None:
        logger.error(
            "[DisplayFieldInitializer] event=display_backfill_write_failed model_id=%s failed_stage=write_instance error_type=%s failure_count=%s",
            model_id,
            type(exc).__name__,
            failure_count,
            exc_info=safe_exception_info(exc),
        )

    def _build_display_fields_for_instance(self, instance: dict, attrs: List[dict], model_id: str) -> Dict[str, str]:
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
            attr_id = attr.get("attr_id")
            attr_type = attr.get("attr_type")

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
                    display_value = self._convert_enum(model_id, attr_id, original_value)
                elif attr_type == FIELD_TYPE_TAG:
                    display_value = self._convert_tag(original_value)
                else:
                    continue

                display_fields[display_field_name] = display_value

            except Exception as e:
                logger.warning(f"[DisplayFieldInitializer] 转换字段 {attr_id} 失败: {e}, " f"使用原始值")
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
                username = user_info.get("username", "")
                display_name = user_info.get("display_name", "")

                # 如果 display_name 存在且不为空，使用 USER_DISPLAY_FORMAT 格式
                # 否则只使用 username
                if display_name and display_name.strip():
                    formatted_users.append(USER_DISPLAY_FORMAT.format(display_name=display_name, username=username))
                else:
                    formatted_users.append(username)
            else:
                # 如果映射中找不到，使用原始ID
                formatted_users.append(str(user_id))

        return DISPLAY_VALUES_SEPARATOR.join(formatted_users)

    def _convert_enum(self, model_id: str, attr_id: str, enum_id: Union[str, List[str]]) -> str:
        """
        将枚举ID转换为枚举名称(从预加载的映射中查询)

        Args:
            model_id: 模型ID
            attr_id: 字段ID
            enum_id: 枚举ID，或多选时的枚举ID列表

        Returns:
            枚举名称；多选时按选项逐项查表后用分隔符拼接
        """
        if not enum_id:
            return ""

        if isinstance(enum_id, list):
            display_names = []
            for option_id in enum_id:
                if not option_id:
                    continue
                # 映射key格式与预加载一致: "model_id.attr_id.option_id"
                map_key = f"{model_id}.{attr_id}.{option_id}"
                enum_name = self._enum_map.get(map_key)
                if enum_name:
                    display_names.append(enum_name)
                else:
                    logger.debug(f"[DisplayFieldInitializer] 未找到枚举映射: {map_key}，使用原始值")
                    display_names.append(str(option_id))
            return DISPLAY_VALUES_SEPARATOR.join(display_names)

        # 构建映射key: "model_id.attr_id.enum_id"
        map_key = f"{model_id}.{attr_id}.{enum_id}"

        # 从预加载的映射中查询
        enum_name = self._enum_map.get(map_key)

        if enum_name:
            return enum_name

        # 降级方案:返回原始ID
        logger.debug(f"[DisplayFieldInitializer] 未找到枚举映射: {map_key}，使用原始值")
        return str(enum_id)

    def _convert_tag(self, tag_values: List[str]) -> str:
        """
        将标签值列表转换为显示字符串

        Args:
            tag_values: 标签值列表，格式为 ["key1:value1", "key2:value2"]

        Returns:
            逗号分隔的标签字符串，如 "env:prod, app:web"
        """
        if not tag_values:
            return ""

        if not isinstance(tag_values, list):
            return str(tag_values)

        return DISPLAY_VALUES_SEPARATOR.join([str(value).strip() for value in tag_values if str(value).strip()])


# 便捷别名
display_field_initializer = DisplayFieldInitializer()
