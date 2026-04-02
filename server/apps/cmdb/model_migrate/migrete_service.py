import ast
import json
from collections import defaultdict
from typing import Any

import pandas as pd
from django.db import transaction

from apps.cmdb.constants.constants import (
    CLASSIFICATION,
    CREATE_CLASSIFICATION_CHECK_ATTR_MAP,
    CREATE_MODEL_CHECK_ATTR,
    ENUM_SELECT_MODE_CHOICES,
    ENUM_SELECT_MODE_DEFAULT,
    INIT_MODEL_GROUP,
    INSTANCE,
    MODEL,
    MODEL_ASSOCIATION,
    ORGANIZATION,
    SUBORDINATE_MODEL,
)
from apps.cmdb.constants.field_constraints import (
    DEFAULT_NUMBER_CONSTRAINT,
    DEFAULT_STRING_CONSTRAINT,
    DEFAULT_TIME_CONSTRAINT,
    StringValidationType,
    TimeDisplayFormat,
    WidgetType,
)
from apps.cmdb.display_field import ExcludeFieldsCache
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.models.public_enum_library import PublicEnumLibrary
from apps.cmdb.services.public_enum_library import enqueue_library_snapshot_refresh
from apps.cmdb.utils.base import get_default_group_id
from apps.cmdb.validators import IdentifierValidator
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

FIELD_GROUP_MANAGER: Any = getattr(FieldGroup, "objects")
PUBLIC_ENUM_LIBRARY_MANAGER: Any = getattr(PublicEnumLibrary, "objects")

EXCEL_STR_TYPE_MAP = {
    "ipv4": StringValidationType.IPV4,
    "ipv6": StringValidationType.IPV6,
    "email": StringValidationType.EMAIL,
    "mobile_phone": StringValidationType.MOBILE_PHONE,
    "phone": StringValidationType.MOBILE_PHONE,
    "url": StringValidationType.URL,
    "json": StringValidationType.JSON,
    "custom": StringValidationType.CUSTOM,
}

EXCEL_WIDGET_MODE_MAP = {
    "single": WidgetType.SINGLE_LINE,
    "multi": WidgetType.MULTI_LINE,
}

EXCEL_TIME_TYPE_MAP = {
    "datetime": TimeDisplayFormat.DATETIME,
    "date": TimeDisplayFormat.DATE,
}


class ModelMigrate:
    DEFAULT_FILE_PATH = "apps/cmdb/support-files/model_config.xlsx"
    PUBLIC_ENUM_LIBRARY_SHEET = "public_enum_libraries"

    def __init__(self, file_source=None, is_pre=True):
        self.file_source = file_source
        self.is_pre = is_pre
        self.model_config = self.get_model_config()
        self.default_group_id = get_default_group_id()

    def get_model_config(self):
        if self.file_source is None:
            source = self.DEFAULT_FILE_PATH
        elif hasattr(self.file_source, "read"):
            from io import BytesIO

            source = BytesIO(self.file_source.read())
        else:
            source = self.file_source

        # 指定第二行（索引1）作为表头，并读取所有 sheet 页
        sheets_dict = pd.read_excel(source, sheet_name=None, header=1)

        sheets_map = {}

        # 遍历所有 sheet 页，并将每个 sheet 页的 DataFrame 转换为列表字典
        for sheet_name, sheet_data in sheets_dict.items():
            # 如果 sheet_data 是 Series（单列数据），转换为 DataFrame
            if isinstance(sheet_data, pd.Series):
                sheet_data = sheet_data.to_frame()  # 将 Series 转换为 DataFrame

            # 对 NaN 值进行填充
            sheet_data = sheet_data.fillna("").infer_objects(copy=False)

            # 将 DataFrame 转换为字典格式，使用 'records' 使每行成为一个字典
            data = sheet_data.to_dict(orient="records")

            sheets_map[sheet_name] = data

        return sheets_map

    def migrate_classifications(self):
        """初始化模型分类"""

        for classification in self.model_config.get("classifications", []):
            classification.update(is_pre=self.is_pre)

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(CLASSIFICATION, [])
            result = ag.batch_create_entity(
                CLASSIFICATION,
                self.model_config.get("classifications", []),
                CREATE_CLASSIFICATION_CHECK_ATTR_MAP,
                exist_items,
            )
        return result

    def _prepare_attr(self, attr):
        attr_id = str(attr.get("attr_id", "")).strip()
        if not attr_id:
            attr_name = str(attr.get("attr_name", "")).strip()
            if attr_name:
                logger.warning("属性定义缺少attr_id，已跳过: attr_name=%s", attr_name)
            return None
        attr["attr_id"] = attr_id

        attr_type = attr.get("attr_type", "str")
        option_value = attr.get("option", "")
        attr["option"] = self._parse_attr_option(attr_type, option_value)

        if attr_type == "enum":
            enum_option, enum_meta = self._normalize_enum_option_payload(attr["option"], attr_id=attr_id)
            attr["option"] = enum_option
            attr["enum_rule_type"] = enum_meta["enum_rule_type"]
            attr["public_library_id"] = enum_meta["public_library_id"]
            attr["enum_select_mode"] = enum_meta["enum_select_mode"]

        user_prompt = attr.get("prompt", "") or attr.get("user_prompt", "")
        attr["user_prompt"] = str(user_prompt) if user_prompt else ""

        return attr

    def model_add_organization(self, model):
        """
        给模型添加组织数据
        """
        _key = INIT_MODEL_GROUP
        model[_key] = self.default_group_id

    def _parse_attr_option(self, attr_type: str, option_value) -> Any:
        if not option_value or option_value == "":
            return self._get_default_option(attr_type)

        try:
            if isinstance(option_value, str):
                parsed = json.loads(option_value.replace("'", '"'))
            elif isinstance(option_value, dict):
                parsed = option_value
            else:
                parsed = ast.literal_eval(str(option_value))
        except (json.JSONDecodeError, ValueError, SyntaxError):
            return self._get_default_option(attr_type)

        if attr_type == "str":
            return self._parse_string_option(parsed)
        elif attr_type in ("int", "float"):
            return self._parse_number_option(parsed)
        elif attr_type == "time":
            return self._parse_time_option(parsed)
        elif attr_type == "enum":
            return parsed if isinstance(parsed, (list, dict)) else []
        elif attr_type == "table":
            return self._parse_table_option(parsed)

        return parsed if isinstance(parsed, dict) else {}

    def _get_default_option(self, attr_type: str) -> Any:
        if attr_type == "str":
            return DEFAULT_STRING_CONSTRAINT.copy()
        elif attr_type in ("int", "float"):
            return DEFAULT_NUMBER_CONSTRAINT.copy()
        elif attr_type == "time":
            return DEFAULT_TIME_CONSTRAINT.copy()
        elif attr_type == "enum":
            return []
        elif attr_type == "table":
            return []
        return {}

    def _parse_string_option(self, parsed: dict) -> dict:
        mode = parsed.get("mode", "single")
        widget_type = EXCEL_WIDGET_MODE_MAP.get(mode, WidgetType.SINGLE_LINE)

        type_value = parsed.get("type")
        if type_value and type_value != "none":
            validation_type = EXCEL_STR_TYPE_MAP.get(type_value, StringValidationType.UNRESTRICTED)
        else:
            validation_type = StringValidationType.UNRESTRICTED

        custom_regex = ""
        if validation_type == StringValidationType.CUSTOM:
            custom_regex = parsed.get("regx", "") or parsed.get("regex", "")

        return {
            "validation_type": validation_type,
            "widget_type": widget_type,
            "custom_regex": custom_regex,
        }

    def _parse_number_option(self, parsed: dict) -> dict:
        result: dict[str, Any] = dict(DEFAULT_NUMBER_CONSTRAINT)

        min_val = parsed.get("min")
        if min_val is not None and min_val != "":
            try:
                result["min_value"] = float(min_val) if "." in str(min_val) else int(min_val)
            except (ValueError, TypeError):
                pass

        max_val = parsed.get("max")
        if max_val is not None and max_val != "":
            try:
                result["max_value"] = float(max_val) if "." in str(max_val) else int(max_val)
            except (ValueError, TypeError):
                pass

        return result

    def _parse_time_option(self, parsed: dict) -> dict:
        type_value = parsed.get("type", "datetime")
        display_format = EXCEL_TIME_TYPE_MAP.get(type_value, TimeDisplayFormat.DATETIME)
        return {"display_format": display_format}

    def _parse_table_option(self, parsed) -> list:
        if not isinstance(parsed, list):
            return []

        result = []
        for col in parsed:
            if not isinstance(col, dict):
                continue

            column_id = col.get("column_id")
            column_name = col.get("column_name")
            column_type = col.get("column_type")
            order = col.get("order")

            if not all([column_id, column_name, column_type, order is not None]):
                continue

            if column_type not in ("str", "number"):
                continue

            try:
                order_int = int(str(order))
                if order_int < 1:
                    continue
            except (ValueError, TypeError):
                continue

            result.append(
                {
                    "column_id": str(column_id),
                    "column_name": str(column_name),
                    "column_type": str(column_type),
                    "order": order_int,
                }
            )

        return result

    @staticmethod
    def _is_empty_row(row: dict) -> bool:
        return not any(str(value).strip() for value in row.values() if value is not None)

    @staticmethod
    def _parse_json_like_value(value, field_name: str, context: str):
        if isinstance(value, (list, dict)):
            return value

        if value in (None, ""):
            raise BaseAppException(f"{context} 的 {field_name} 不能为空")

        try:
            if isinstance(value, str):
                return json.loads(value.replace("'", '"'))
            return ast.literal_eval(str(value))
        except (json.JSONDecodeError, ValueError, SyntaxError):
            raise BaseAppException(f"{context} 的 {field_name} 不是合法的 JSON/数组格式")

    def _normalize_public_enum_options(self, options_value, context: str) -> list[dict]:
        options = self._parse_json_like_value(options_value, "options", context)
        if not isinstance(options, list) or not options:
            raise BaseAppException(f"{context} 的 options 必须是非空数组")

        normalized = []
        seen_ids = set()
        for idx, item in enumerate(options, start=1):
            if not isinstance(item, dict):
                raise BaseAppException(f"{context} 的 options[{idx}] 必须是对象")
            option_id = str(item.get("id", "")).strip()
            option_name = str(item.get("name", "")).strip()
            if not option_id:
                raise BaseAppException(f"{context} 的 options[{idx}].id 不能为空")
            if not option_name:
                raise BaseAppException(f"{context} 的 options[{idx}].name 不能为空")
            if option_id in seen_ids:
                raise BaseAppException(f"{context} 的 options 存在重复 id: {option_id}")
            seen_ids.add(option_id)
            normalized.append({"id": option_id, "name": option_name})
        return normalized

    @staticmethod
    def _normalize_attr_enum_options(options_value, context: str) -> list[dict]:
        if options_value in (None, "", []):
            return []
        if not isinstance(options_value, list):
            raise BaseAppException(f"{context} 的 option 必须是数组")

        normalized = []
        seen_ids = set()
        for idx, item in enumerate(options_value, start=1):
            if not isinstance(item, dict):
                raise BaseAppException(f"{context} 的 option[{idx}] 必须是对象")
            option_id = str(item.get("id", "")).strip()
            option_name = str(item.get("name", "")).strip()
            if not option_id:
                raise BaseAppException(f"{context} 的 option[{idx}].id 不能为空")
            if not option_name:
                raise BaseAppException(f"{context} 的 option[{idx}].name 不能为空")
            if option_id in seen_ids:
                raise BaseAppException(f"{context} 的 option 存在重复 id: {option_id}")
            seen_ids.add(option_id)
            normalized.append({"id": option_id, "name": option_name})
        return normalized

    def _normalize_team_value(self, team_value, context: str) -> list:
        team = self._parse_json_like_value(team_value, "team", context)
        if not isinstance(team, list):
            raise BaseAppException(f"{context} 的 team 必须是数组")
        return team

    def _normalize_enum_option_payload(self, parsed_option, attr_id: str = "") -> tuple[list[dict], dict[str, Any]]:
        context = f"属性 {attr_id}" if attr_id else "枚举属性"

        if isinstance(parsed_option, list):
            option = self._normalize_attr_enum_options(parsed_option, context)
            return option, {
                "enum_rule_type": "custom",
                "public_library_id": None,
                "enum_select_mode": ENUM_SELECT_MODE_DEFAULT,
            }

        if not isinstance(parsed_option, dict):
            raise BaseAppException(f"{context} 的 option 配置不合法")

        enum_rule_type = str(parsed_option.get("enum_rule_type", "custom")).strip() or "custom"
        public_library_id = parsed_option.get("public_library_id")
        enum_select_mode = str(parsed_option.get("enum_select_mode", ENUM_SELECT_MODE_DEFAULT)).strip() or ENUM_SELECT_MODE_DEFAULT
        if enum_select_mode not in ENUM_SELECT_MODE_CHOICES:
            raise BaseAppException(f"{context} 的 enum_select_mode 不合法: {enum_select_mode}")

        nested_option = parsed_option.get("option")

        if enum_rule_type == "public_library":
            public_library_id = str(public_library_id or "").strip()
            if not public_library_id:
                raise BaseAppException(f"{context} 使用公共选项库时 public_library_id 不能为空")

            option = self._normalize_attr_enum_options(nested_option if nested_option is not None else [], context)
            if not option:
                library = PUBLIC_ENUM_LIBRARY_MANAGER.filter(library_id=public_library_id).first()
                if library and isinstance(library.options, list):
                    option = self._normalize_attr_enum_options(library.options, context)

            return option, {
                "enum_rule_type": "public_library",
                "public_library_id": public_library_id,
                "enum_select_mode": enum_select_mode,
            }

        if enum_rule_type != "custom":
            raise BaseAppException(f"{context} 的 enum_rule_type 不合法: {enum_rule_type}")

        option = self._normalize_attr_enum_options(nested_option if nested_option is not None else [], context)
        return option, {
            "enum_rule_type": "custom",
            "public_library_id": None,
            "enum_select_mode": enum_select_mode,
        }

    def _normalize_public_enum_library_row(self, row: dict, row_number: int) -> dict:
        context = f"sheet[{self.PUBLIC_ENUM_LIBRARY_SHEET}] 第 {row_number} 行"
        library_id = str(row.get("library_id", "")).strip()
        name = str(row.get("name", "")).strip()
        if not library_id:
            raise BaseAppException(f"{context} 的 library_id 不能为空")
        if not IdentifierValidator.is_valid(library_id):
            raise BaseAppException(f"{context} 的 library_id 非法: {library_id}")
        if not name:
            raise BaseAppException(f"{context} 的 name 不能为空")

        return {
            "library_id": library_id,
            "name": name,
            "team": self._normalize_team_value(row.get("team"), context),
            "options": self._normalize_public_enum_options(row.get("options"), context),
        }

    def migrate_public_enum_libraries(self):
        rows = self.model_config.get(self.PUBLIC_ENUM_LIBRARY_SHEET, [])
        if not rows:
            return {"created": 0, "updated": 0, "skipped": 0, "sheet_present": False}

        normalized_rows = []
        seen_library_ids = set()
        for index, row in enumerate(rows, start=3):
            if self._is_empty_row(row):
                continue
            normalized = self._normalize_public_enum_library_row(row, index)
            library_id = normalized["library_id"]
            if library_id in seen_library_ids:
                raise BaseAppException(f"sheet[{self.PUBLIC_ENUM_LIBRARY_SHEET}] 存在重复 library_id: {library_id}")
            seen_library_ids.add(library_id)
            normalized_rows.append(normalized)

        created = 0
        updated = 0
        skipped = 0
        updated_library_ids = []

        with transaction.atomic():
            for payload in normalized_rows:
                library = PUBLIC_ENUM_LIBRARY_MANAGER.filter(library_id=payload["library_id"]).first()
                if not library:
                    PUBLIC_ENUM_LIBRARY_MANAGER.create(
                        library_id=payload["library_id"],
                        name=payload["name"],
                        team=payload["team"],
                        options=payload["options"],
                        created_by="system",
                        updated_by="system",
                    )
                    created += 1
                    continue

                changed = library.name != payload["name"] or library.team != payload["team"] or library.options != payload["options"]
                if not changed:
                    skipped += 1
                    continue

                library.name = payload["name"]
                library.team = payload["team"]
                library.options = payload["options"]
                library.updated_by = "system"
                library.save(update_fields=["name", "team", "options", "updated_by", "updated_at"])
                updated += 1
                updated_library_ids.append(payload["library_id"])

        for library_id in updated_library_ids:
            enqueue_library_snapshot_refresh(library_id, trigger="model_config_import", operator="system")

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "sheet_present": True,
        }

    def _validate_public_library_references(self, attrs_by_model_id: dict[str, list[dict]]):
        referenced_library_ids = set()
        for model_id, attrs in attrs_by_model_id.items():
            for attr in attrs:
                if attr.get("attr_type") != "enum":
                    continue
                if attr.get("enum_rule_type", "custom") != "public_library":
                    continue

                public_library_id = str(attr.get("public_library_id") or "").strip()
                if not public_library_id:
                    raise BaseAppException(f"模型 {model_id} 的属性 {attr.get('attr_id')} 缺少 public_library_id")
                referenced_library_ids.add(public_library_id)

        if not referenced_library_ids:
            return

        existing_library_ids = set(PUBLIC_ENUM_LIBRARY_MANAGER.filter(library_id__in=referenced_library_ids).values_list("library_id", flat=True))
        missing_library_ids = sorted(referenced_library_ids - existing_library_ids)
        if missing_library_ids:
            raise BaseAppException("模型枚举字段引用了不存在的公共选项库: " + ", ".join(missing_library_ids))

    def _build_model_payload(self):
        models = []
        attrs_by_model_id = {}

        for model in self.model_config.get("models", []):
            model_id = model.get("model_id", "")
            if not IdentifierValidator.is_valid(model_id):
                logger.warning(f"跳过无效模型ID: {model_id}")
                continue

            model_data = dict(model)
            model_data.update(is_pre=self.is_pre)
            self.model_add_organization(model_data)

            attr_key = f"attr-{model_id}"
            attrs = self.model_config.get(attr_key, [])
            prepared_attrs = []
            attr_id_set = set()

            for attr in attrs:
                prepared = self._prepare_attr(dict(attr))
                if not prepared:
                    continue

                attr_id = prepared.get("attr_id")
                if attr_id in attr_id_set:
                    logger.warning(f"模型 {model_id} 存在重复属性ID: {attr_id}，跳过重复定义")
                    continue

                attr_id_set.add(attr_id)
                prepared["is_pre"] = self.is_pre
                prepared_attrs.append(prepared)

            attrs_by_model_id[model_id] = prepared_attrs
            models.append({**model_data, "attrs": json.dumps(prepared_attrs, ensure_ascii=False)})

        return models, attrs_by_model_id

    @staticmethod
    def _parse_model_attrs(attrs_value):
        if isinstance(attrs_value, list):
            attrs = attrs_value
        else:
            try:
                attrs = json.loads(attrs_value or "[]")
            except (json.JSONDecodeError, TypeError):
                attrs = []

        return attrs if isinstance(attrs, list) else []

    @staticmethod
    def _merge_existing_attr_config(existing_attr: dict, incoming_attr: dict) -> bool:
        changed = False

        attr_name = str(incoming_attr.get("attr_name", "")).strip()
        if attr_name and existing_attr.get("attr_name") != attr_name:
            existing_attr["attr_name"] = attr_name
            changed = True

        if "user_prompt" in incoming_attr:
            user_prompt = str(incoming_attr.get("user_prompt") or "")
            if existing_attr.get("user_prompt", "") != user_prompt:
                existing_attr["user_prompt"] = user_prompt
                changed = True

        if "option" in incoming_attr and existing_attr.get("option") != incoming_attr.get("option"):
            existing_attr["option"] = incoming_attr.get("option")
            changed = True

        # 布尔约束仅接受布尔值，避免 Excel 空值/字符串造成脏覆盖。
        for key in ("is_only", "is_required", "editable"):
            value = incoming_attr.get(key)
            if isinstance(value, bool) and existing_attr.get(key) != value:
                existing_attr[key] = value
                changed = True

        return changed

    def _sync_added_attrs_to_existing_models(self, ag, attrs_by_model_id, existing_model_map):
        target_model_ids = [model_id for model_id in attrs_by_model_id.keys() if model_id in existing_model_map]
        if not target_model_ids:
            return {
                "updated_models": [],
                "added_attr_count": 0,
                "updated_attr_count": 0,
                "updated_group_count": 0,
                "created_group_count": 0,
            }

        field_groups = FIELD_GROUP_MANAGER.filter(model_id__in=target_model_ids).order_by("model_id", "order")
        field_group_map = {}
        max_group_order = defaultdict(int)
        for group in field_groups:
            field_group_map[(group.model_id, group.group_name)] = group
            if group.order > max_group_order[group.model_id]:
                max_group_order[group.model_id] = group.order

        updated_models = []
        added_attr_count = 0
        updated_attr_count = 0
        updated_group_count = 0
        created_group_count = 0

        for model_id in target_model_ids:
            existing_model = existing_model_map[model_id]
            existing_attrs = self._parse_model_attrs(existing_model.get("attrs", "[]"))
            existing_attr_map = {
                attr.get("attr_id"): attr
                for attr in existing_attrs
                if isinstance(attr, dict) and attr.get("attr_id")
            }
            existing_attr_ids = {attr.get("attr_id") for attr in existing_attrs if isinstance(attr, dict) and attr.get("attr_id")}

            added_attrs = []
            model_updated_attr_count = 0
            for attr in attrs_by_model_id.get(model_id, []):
                attr_id = attr.get("attr_id")
                if not attr_id:
                    continue

                existing_attr = existing_attr_map.get(attr_id)
                if existing_attr:
                    # 命中同 attr_id：做配置更新而非重复追加。
                    if self._merge_existing_attr_config(existing_attr, attr):
                        model_updated_attr_count += 1
                    continue

                existing_attr_ids.add(attr_id)
                added_attrs.append(attr)

            if not added_attrs and model_updated_attr_count == 0:
                continue

            merged_attrs = [*existing_attrs, *added_attrs]
            ag.set_entity_properties(
                MODEL,
                [existing_model["_id"]],
                {"attrs": json.dumps(merged_attrs, ensure_ascii=False)},
                {},
                [],
                False,
            )

            model_group_updates = 0
            model_group_creates = 0
            if added_attrs:
                model_group_updates, model_group_creates = self._sync_added_attrs_field_groups(
                    model_id=model_id,
                    added_attrs=added_attrs,
                    field_group_map=field_group_map,
                    max_group_order=max_group_order,
                )

            updated_group_count += model_group_updates
            created_group_count += model_group_creates
            added_attr_count += len(added_attrs)
            updated_attr_count += model_updated_attr_count
            updated_models.append(model_id)

        if updated_models:
            # 导入批次内统一刷新一次缓存，避免每模型触发全量刷新导致耗时放大。
            ExcludeFieldsCache.refresh_cache()

        return {
            "updated_models": updated_models,
            "added_attr_count": added_attr_count,
            "updated_attr_count": updated_attr_count,
            "updated_group_count": updated_group_count,
            "created_group_count": created_group_count,
        }

    @staticmethod
    def _sync_added_attrs_field_groups(model_id, added_attrs, field_group_map, max_group_order):
        group_attr_map = {}
        for attr in added_attrs:
            attr_id = attr.get("attr_id")
            if not attr_id:
                continue
            group_name = (attr.get("attr_group") or "默认分组").strip() or "默认分组"
            group_attr_map.setdefault(group_name, [])
            group_attr_map[group_name].append(attr_id)

        updated_group_count = 0
        created_group_count = 0

        for group_name, incoming_attr_ids in group_attr_map.items():
            unique_attr_ids = []
            unique_attr_id_set = set()
            for attr_id in incoming_attr_ids:
                if attr_id in unique_attr_id_set:
                    continue
                unique_attr_id_set.add(attr_id)
                unique_attr_ids.append(attr_id)

            group_key = (model_id, group_name)
            group = field_group_map.get(group_key)

            if group:
                current_orders = group.attr_orders if isinstance(group.attr_orders, list) else []
                current_order_set = set(current_orders)
                append_attr_ids = [attr_id for attr_id in unique_attr_ids if attr_id not in current_order_set]
                if not append_attr_ids:
                    continue

                group.attr_orders = [*current_orders, *append_attr_ids]
                group.save(update_fields=["attr_orders"])
                updated_group_count += 1
                continue

            max_group_order[model_id] += 1
            group = FIELD_GROUP_MANAGER.create(
                model_id=model_id,
                group_name=group_name,
                order=max_group_order[model_id],
                is_collapsed=False,
                attr_orders=unique_attr_ids,
                created_by="system",
            )
            field_group_map[group_key] = group
            created_group_count += 1

        return updated_group_count, created_group_count

    def migrate_models(self):
        """初始化模型"""
        models, attrs_by_model_id = self._build_model_payload()
        self._validate_public_library_references(attrs_by_model_id)

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(MODEL, [])
            exist_model_map = {item.get("model_id"): item for item in exist_items}
            exist_classifications, _ = ag.query_entity(CLASSIFICATION, [])
            classification_map = {i["classification_id"]: i["_id"] for i in exist_classifications}
            models = [i for i in models if i.get("classification_id") in classification_map]
            new_models = [i for i in models if i.get("model_id") not in exist_model_map]
            result = ag.batch_create_entity(MODEL, new_models, CREATE_MODEL_CHECK_ATTR, exist_items) if new_models else []

            success_models = [i["data"] for i in result if i["success"]]
            asso_list = [
                dict(
                    src_id=classification_map[i["classification_id"]],
                    dst_id=i["_id"],
                    classification_model_asst_id=f"{i['classification_id']}_{SUBORDINATE_MODEL}_{i['model_id']}",
                )
                for i in success_models
            ]
            asso_result = (
                ag.batch_create_edge(
                    SUBORDINATE_MODEL,
                    CLASSIFICATION,
                    MODEL,
                    asso_list,
                    "classification_model_asst_id",
                )
                if asso_list
                else []
            )

            sync_result = self._sync_added_attrs_to_existing_models(
                ag=ag,
                attrs_by_model_id=attrs_by_model_id,
                existing_model_map=exist_model_map,
            )

        if sync_result["updated_models"]:
            logger.info(
                "同步模型属性完成: 更新模型=%s, 新增属性=%s, 更新属性=%s, 更新分组=%s, 新建分组=%s",
                len(sync_result["updated_models"]),
                sync_result["added_attr_count"],
                sync_result["updated_attr_count"],
                sync_result["updated_group_count"],
                sync_result["created_group_count"],
            )

        # 为成功创建的模型创建 FieldGroup 记录
        self._create_field_groups(success_models)

        return result, asso_result

    @staticmethod
    def _create_field_groups(success_models):
        """为成功创建的模型创建 FieldGroup 记录"""
        for model_data in success_models:
            model_id = model_data.get("model_id")
            if not model_id:
                continue

            try:
                attrs = json.loads(model_data.get("attrs", "[]"))
            except (json.JSONDecodeError, TypeError):
                attrs = []

            if not attrs:
                continue

            group_attrs_map = {}
            group_order = []

            for attr in attrs:
                group_name = attr.get("attr_group") or "默认分组"
                attr_id = attr.get("attr_id")

                if group_name not in group_attrs_map:
                    group_attrs_map[group_name] = []
                    group_order.append(group_name)

                if attr_id:
                    group_attrs_map[group_name].append(attr_id)

            for order, group_name in enumerate(group_order, start=1):
                attr_ids = group_attrs_map.get(group_name, [])
                FIELD_GROUP_MANAGER.get_or_create(
                    model_id=model_id,
                    group_name=group_name,
                    defaults={
                        "order": order,
                        "is_collapsed": False,
                        "attr_orders": attr_ids,
                        "created_by": "system",
                    },
                )

    def migrate_associations(self):
        """初始模型关联"""
        associations = []
        for model in self.model_config.get("models", []):
            asso_key = f"asso-{model['model_id']}"
            if asso_key in self.model_config:
                associations.extend(self.model_config[asso_key])

        for association in associations:
            association.update(is_pre=self.is_pre)

        with GraphClient() as ag:
            models, _ = ag.query_entity(MODEL, [])
            model_map = {i["model_id"]: i["_id"] for i in models}
            asso_list = [
                dict(
                    dst_id=model_map.get(i["dst_model_id"]),
                    src_id=model_map.get(i["src_model_id"]),
                    model_asst_id=f"{i['src_model_id']}_{i['asst_id']}_{i['dst_model_id']}",
                    **i,
                )
                for i in associations
                if model_map.get(i["src_model_id"]) and model_map.get(i["dst_model_id"])
            ]
            result = ag.batch_create_edge(MODEL_ASSOCIATION, MODEL, MODEL, asso_list, "model_asst_id")
        return result

    def main(self):
        # 创建模型分类
        classification_resp = self.migrate_classifications()
        public_enum_library_resp = self.migrate_public_enum_libraries()
        # 创建模型
        model_resp, classification_asso_resp = self.migrate_models()

        # 创建模型关联
        association_resp = self.migrate_associations()

        try:
            # 检查并补充旧模型的组织字段
            self.check_and_update_old_models_group()
        except Exception as err:  # noqa
            import traceback

            logger.error(f"Error updating old models group: {traceback.format_exc()}")

        try:
            # 检查并修复旧实例的 organization 字段类型
            self.check_and_update_old_instances_organization()
        except Exception as err:  # noqa
            import traceback

            logger.error(f"Error updating old instances organization: {traceback.format_exc()}")

        return dict(
            classification=classification_resp,
            public_enum_libraries=public_enum_library_resp,
            model=model_resp,
            classification_assos=classification_asso_resp,
            association=association_resp,
        )

    def check_and_update_old_models_group(self):
        """检查并补充旧模型的组织字段"""
        with GraphClient() as ag:
            # 查询所有模型
            all_models, _ = ag.query_entity(MODEL, [])

            # 筛选出没有组织字段的模型
            models_without_group = []
            for model in all_models:
                if INIT_MODEL_GROUP not in model or not model[INIT_MODEL_GROUP]:
                    models_without_group.append(model["_id"])
                elif INIT_MODEL_GROUP in model and isinstance(model[INIT_MODEL_GROUP], int):
                    # 如果组织字段是单个整数，转换为列表
                    models_without_group.append(model["_id"])

            # 批量更新缺少组织字段的模型
            if models_without_group:
                ag.batch_update_node_properties(
                    label=MODEL,
                    node_ids=models_without_group,
                    properties={INIT_MODEL_GROUP: self.default_group_id},
                )

    def check_and_update_old_instances_organization(self):
        """检查并修复旧实例的 organization 字段类型

        将单个整数类型的 organization 转换为列表类型，以保持与模型定义一致
        """
        with GraphClient() as ag:
            # 查询所有实例
            all_instances, _ = ag.query_entity(INSTANCE, [])

            # 筛选出 organization 字段为整数类型的实例
            instances_need_fix = []
            for instance in all_instances:
                # 如果 organization 字段存在且是整数类型，需要转换为列表
                if ORGANIZATION in instance and isinstance(instance[ORGANIZATION], int):
                    instances_need_fix.append(instance["_id"])
                # 如果 organization 字段不存在或为空，设置为默认组织列表
                elif ORGANIZATION not in instance or not instance[ORGANIZATION]:
                    instances_need_fix.append(instance["_id"])

            # 批量更新需要修复的实例
            if instances_need_fix:
                logger.info(f"Found {len(instances_need_fix)} instances with incorrect organization field type")
                ag.batch_update_node_properties(
                    label=INSTANCE,
                    node_ids=instances_need_fix,
                    properties={ORGANIZATION: self.default_group_id},
                )
                logger.info(f"Successfully updated {len(instances_need_fix)} instances organization field to list type")
