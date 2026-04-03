import ast
import json
import re

import openpyxl

from apps.cmdb.constants.constants import (
    INSTANCE,
    NEED_CONVERSION_TYPE,
    ORGANIZATION,
    USER,
    ENUM,
    INSTANCE_ASSOCIATION,
    ModelConstraintKey,
    ENUM_SELECT_MODE_MULTIPLE,
    ENUM_SELECT_MODE_DEFAULT,
)
from apps.cmdb.constants.field_constraints import TAG_ATTR_ID, TAG_MODE_FREE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models import CREATE_INST_ASST
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.unique_rule import build_unique_rule_context
from apps.cmdb.validators.field_validator import (
    normalize_tag_field_option,
    normalize_tag_input_values,
    validate_tag_values,
)
from apps.cmdb.utils.change_record import create_change_record_by_asso
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.system_mgmt.models import Group


class Import:
    def __init__(self, model_id, attrs, exist_items, operator):
        self.model_id = model_id
        self.attrs = attrs
        self.exist_items = exist_items
        self.operator = operator
        self.inst_name_id_map = {}
        self.inst_id_name_map = {}
        self.inst_list = []
        self.import_result_message = {
            "add": {"success": 0, "error": 0, "data": []},
            "update": {"success": 0, "error": 0, "data": []},
            "asso": {"success": 0, "error": 0, "data": []},
        }
        self.model_asso_map = self.get_model_asso_map()
        # 用于收集数据验证错误
        self.validation_errors = []
        # 缓存的字段映射，由 _build_field_maps 初始化
        self._field_maps = None

    @staticmethod
    def _normalize_user_token(token):
        """将Excel中的用户显示值规范化为username。

        支持：
        - username
        - 显示名(username)
        - 显示名（username）
        """
        if token is None:
            return None
        s = str(token).strip()
        if not s:
            return ""
        # 兼容英文括号与中文括号
        if s.endswith(")") and "(" in s:
            return s.rsplit("(", 1)[-1].rstrip(")").strip()
        if s.endswith("）") and "（" in s:
            return s.rsplit("（", 1)[-1].rstrip("）").strip()
        return s

    def _build_field_maps(self):
        """构建字段类型映射表，用于Excel数据解析。

        Returns:
            dict: 包含各类字段映射的字典
        """
        field_maps = {
            "need_val_to_id": {},  # 需要值到ID转换的字段（枚举、组织、用户）
            "need_update_type": {},  # 需要类型转换的字段
            "org_user": {},  # 组织/用户字段标识
            "table_fields": set(),  # 表格字段
            "tag_fields": set(),  # 标签字段
            "enum_select_mode": {},  # 枚举字段选择模式
            "attr_name_map": {},  # 属性ID到名称的映射
        }

        for attr_info in self.attrs:
            attr_id = attr_info["attr_id"]
            attr_type = attr_info["attr_type"]
            field_maps["attr_name_map"][attr_id] = attr_info["attr_name"]

            if attr_type in NEED_CONVERSION_TYPE:
                field_maps["need_update_type"][attr_id] = attr_type
            elif attr_type == "table":
                field_maps["table_fields"].add(attr_id)
            elif attr_type == "tag":
                field_maps["tag_fields"].add(attr_id)
            elif attr_type in {ORGANIZATION, USER, ENUM}:
                field_maps["need_val_to_id"][attr_id] = {i["name"]: i["id"] for i in attr_info["option"]}
                if attr_type in {ORGANIZATION, USER}:
                    field_maps["org_user"][attr_id] = attr_type
                if attr_type == ENUM:
                    field_maps["enum_select_mode"][attr_id] = attr_info.get("enum_select_mode", ENUM_SELECT_MODE_DEFAULT)

        return field_maps

    def _process_type_conversion_field(self, key, value, row_index, field_maps):
        """处理需要类型转换的字段。

        Returns:
            tuple: (converted_value, error_msg)
        """
        try:
            method = NEED_CONVERSION_TYPE[field_maps["need_update_type"][key]]
            return method(value), None
        except (ValueError, TypeError):
            attr_name = field_maps["attr_name_map"].get(key, key)
            return None, f"第{row_index}行，字段'{attr_name}'的值'{value}'格式错误"

    def _process_table_field(self, key, value, row_index, field_maps):
        """处理表格字段。

        Returns:
            tuple: (parsed_value, error_msg)
        """
        try:
            if isinstance(value, str):
                return json.loads(value), None
            return value, None
        except (json.JSONDecodeError, TypeError):
            attr_name = field_maps["attr_name_map"].get(key, key)
            return None, f"第{row_index}行，字段'{attr_name}'的表格数据JSON格式错误"

    def _process_tag_field(self, key, value, row_index, field_maps):
        """处理标签字段。

        Returns:
            tuple: (normalized_value, error_msg)
        """
        try:
            return normalize_tag_input_values(value), None
        except Exception:
            attr_name = field_maps["attr_name_map"].get(key, key)
            return None, f"第{row_index}行，字段'{attr_name}'标签格式解析失败"

    def _process_org_user_field(self, key, value, row_index, field_maps, allowed_org_set):
        """处理组织/用户字段。

        Returns:
            tuple: (enum_ids, error_msg, organization_cell_provided)
        """
        # 解析值列表
        if not isinstance(value, list):
            if "," in str(value):
                value_list = str(value).split(",")
            elif "，" in str(value):
                value_list = str(value).split("，")
            else:
                value_list = [str(value)]
        else:
            value_list = value

        field_type = field_maps["org_user"][key]

        # 组织字段特殊处理
        if field_type == ORGANIZATION:
            return self._resolve_organization_ids(
                value_list=value_list,
                allowed_org_set=allowed_org_set,
                row_index=row_index,
                field_display_name=field_maps["attr_name_map"].get(key, key),
            )

        # 用户字段处理
        enum_id = []
        invalid_values = []
        for val in value_list:
            raw_val = val
            lookup_val = self._normalize_user_token(val)
            mapped_id = field_maps["need_val_to_id"][key].get(lookup_val)
            if mapped_id is not None:
                enum_id.append(mapped_id)
            else:
                invalid_values.append(raw_val)

        # 用户字段结果处理
        # if key != "operator":
        #     if len(enum_id) >= 1:
        #         enum_id = enum_id[0]

        if invalid_values:
            logger.warning(field_maps["need_val_to_id"][key])
            attr_name = field_maps["attr_name_map"].get(key, key)
            return None, f"第{row_index}行，字段'{attr_name}'的值'{invalid_values}'无效", False

        return enum_id, None, False

    def _process_enum_field(self, key, value, row_index, field_maps):
        """处理枚举字段。

        Returns:
            tuple: (enum_ids, error_msg)
        """
        select_mode = field_maps["enum_select_mode"].get(key, ENUM_SELECT_MODE_DEFAULT)
        attr_name = field_maps["attr_name_map"].get(key, key)

        if select_mode == ENUM_SELECT_MODE_MULTIPLE:
            # 多选枚举处理
            if isinstance(value, list):
                value_list = value
            elif isinstance(value, str):
                if "," in value:
                    value_list = [v.strip() for v in value.split(",") if v.strip()]
                elif "，" in value:
                    value_list = [v.strip() for v in value.split("，") if v.strip()]
                else:
                    value_list = [value.strip()] if value.strip() else []
            else:
                value_list = [str(value)] if value else []

            enum_ids = []
            invalid_enum_values = []
            for val in value_list:
                mapped_id = field_maps["need_val_to_id"][key].get(val)
                if mapped_id is not None:
                    enum_ids.append(mapped_id)
                else:
                    invalid_enum_values.append(val)

            if invalid_enum_values:
                return None, f"第{row_index}行，字段'{attr_name}'的值'{invalid_enum_values}'无效"

            return enum_ids, None
        else:
            # 单选枚举处理
            enum_id = field_maps["need_val_to_id"][key].get(value)
            if enum_id is not None:
                return [enum_id], None
            return None, f"第{row_index}行，字段'{attr_name}'的值'{value}'无效"

    def _resolve_organization_ids(
        self,
        value_list: list,
        allowed_org_set: set,
        row_index: int,
        field_display_name: str,
    ):
        """解析组织字段，支持组织名与路径(Default/xxx)，并按 allowed_org_set 做范围校验。

        Returns:
            tuple[list[int], str|None, bool]: (org_ids, error_msg, organization_cell_provided)
        """

        normalized_values = [v.strip() if isinstance(v, str) else v for v in (value_list or [])]
        organization_cell_provided = any(v not in (None, "") for v in normalized_values)

        if not organization_cell_provided:
            return [], None, False

        query_names = set()
        for raw in normalized_values:
            if not raw:
                continue
            if isinstance(raw, str) and "/" in raw:
                parts = [p.strip() for p in raw.split("/") if p.strip()]
                if parts:
                    query_names.add(parts[-1])
                    if len(parts) >= 2:
                        query_names.add(parts[-2])
            else:
                query_names.add(raw)

        # 先在全量组织表中定位，再根据 allowed_org_set 判定“越界”还是“无效”
        group_rows = list(Group.objects.filter(name__in=query_names).values("id", "name", "parent_id"))

        parent_ids = {r["parent_id"] for r in group_rows if r.get("parent_id")}
        parent_name_map = {}
        if parent_ids:
            parent_name_map = {r["id"]: r["name"] for r in Group.objects.filter(id__in=parent_ids).values("id", "name")}

        rows_by_name = {}
        for r in group_rows:
            rows_by_name.setdefault(r["name"], []).append(r)

        enum_id = []
        invalid_values = []
        out_of_scope_values = []

        for raw in normalized_values:
            if not raw:
                continue

            if isinstance(raw, str) and "/" in raw:
                parts = [p.strip() for p in raw.split("/") if p.strip()]
                if not parts:
                    invalid_values.append(raw)
                    continue

                leaf_name = parts[-1]
                parent_name = parts[-2] if len(parts) >= 2 else None
                candidates = rows_by_name.get(leaf_name, [])
                if parent_name:
                    candidates = [c for c in candidates if parent_name_map.get(c.get("parent_id")) == parent_name]

                if not candidates:
                    invalid_values.append(raw)
                    continue

                if allowed_org_set is None:
                    return (
                        [],
                        f"第{row_index}行，字段'{field_display_name}'缺少组织范围上下文，请刷新后重试",
                        organization_cell_provided,
                    )

                in_scope = [c for c in candidates if c["id"] in allowed_org_set]
                if len(in_scope) == 1:
                    mapped_id = in_scope[0]["id"]
                elif len(in_scope) == 0:
                    out_of_scope_values.append(raw)
                    continue
                else:
                    invalid_values.append(raw)
                    continue

            else:
                candidates = rows_by_name.get(raw, [])
                if not candidates:
                    invalid_values.append(raw)
                    continue

                if allowed_org_set is None:
                    if len(candidates) == 1:
                        mapped_id = candidates[0]["id"]
                    else:
                        invalid_values.append(raw)
                        continue
                else:
                    in_scope = [c for c in candidates if c["id"] in allowed_org_set]
                    if len(in_scope) == 1:
                        mapped_id = in_scope[0]["id"]
                    elif len(in_scope) == 0:
                        out_of_scope_values.append(raw)
                        continue
                    else:
                        invalid_values.append(raw)
                        continue

            enum_id.append(mapped_id)

        if invalid_values:
            return (
                [],
                f"第{row_index}行，字段'{field_display_name}'的值'{invalid_values}'无效",
                organization_cell_provided,
            )

        if out_of_scope_values:
            return (
                [],
                f"第{row_index}行，字段'{field_display_name}'的值'{out_of_scope_values}'不在当前选择组织范围内",
                organization_cell_provided,
            )

        return enum_id, None, organization_cell_provided

    def _process_cell_value(self, key, value, row_index, field_maps, allowed_org_set, item):
        """处理单个单元格的值。

        Args:
            key: 字段键名
            value: 单元格值
            row_index: 行号
            field_maps: 字段映射表
            allowed_org_set: 允许的组织ID集合
            item: 当前行数据字典

        Returns:
            tuple: (should_continue, error_msg, organization_cell_provided)
        """
        organization_cell_provided = False

        # 处理类型转换字段
        if key in field_maps["need_update_type"]:
            converted, error_msg = self._process_type_conversion_field(key, value, row_index, field_maps)
            if error_msg:
                return True, error_msg, organization_cell_provided
            item[key] = converted
            return True, None, organization_cell_provided

        # 处理表格字段
        if key in field_maps["table_fields"]:
            parsed, error_msg = self._process_table_field(key, value, row_index, field_maps)
            if error_msg:
                return True, error_msg, organization_cell_provided
            item[key] = parsed
            return True, None, organization_cell_provided

        # 处理标签字段
        if key in field_maps["tag_fields"]:
            normalized, error_msg = self._process_tag_field(key, value, row_index, field_maps)
            if error_msg:
                return True, error_msg, organization_cell_provided
            item[key] = normalized
            return True, None, organization_cell_provided

        # 处理枚举/组织/用户字段
        if key in field_maps["need_val_to_id"]:
            if key in field_maps["org_user"]:
                enum_id, error_msg, provided = self._process_org_user_field(key, value, row_index, field_maps, allowed_org_set)
                organization_cell_provided = provided
                if error_msg:
                    return True, error_msg, organization_cell_provided
                if enum_id:
                    item[key] = enum_id
            else:
                enum_ids, error_msg = self._process_enum_field(key, value, row_index, field_maps)
                if error_msg:
                    return True, error_msg, organization_cell_provided
                if enum_ids:
                    item[key] = enum_ids
            return True, None, organization_cell_provided

        # 普通字段直接赋值
        return False, None, organization_cell_provided

    def _process_excel_row(self, row, keys, row_index, field_maps, allowed_org_set, asso_key_map):
        """处理Excel中的一行数据。

        Returns:
            tuple: (item_dict, has_data, has_errors)
        """
        item = {"model_id": self.model_id}
        inst_name = ""
        row_has_data = False
        row_validation_errors_count = len(self.validation_errors)

        for i, cell in enumerate(row):
            try:
                value = ast.literal_eval(cell.value)
            except Exception:  # noqa: BLE001 - 字面量解析失败时使用原始值
                value = cell.value

            if not value:
                continue

            row_has_data = True
            key = keys[i]

            if key == "inst_name":
                inst_name = value

            # 处理关联字段
            if key in asso_key_map:
                if inst_name:
                    split_value = value.split(",")
                    asso_key_map[key].setdefault(inst_name, []).extend(split_value)
                continue

            # 处理单元格值
            handled, error_msg, _ = self._process_cell_value(key, value, row_index, field_maps, allowed_org_set, item)

            if error_msg:
                self.validation_errors.append(error_msg)
                logger.warning(error_msg)
                continue

            # 普通字段直接赋值
            if not handled:
                item[key] = value

        row_has_validation_errors = len(self.validation_errors) > row_validation_errors_count

        return item, row_has_data, row_has_validation_errors

    def format_excel_data(self, excel_meta: bytes, allowed_org_ids: list = None):
        """格式化excel数据。

        Args:
            excel_meta: Excel文件字节流
            allowed_org_ids: 允许的组织ID列表

        Returns:
            tuple: (result_list, asso_key_map)
        """
        allowed_org_set = set(allowed_org_ids) if allowed_org_ids is not None else None

        # 构建字段映射
        field_maps = self._build_field_maps()

        # 读取Excel文件
        wb = openpyxl.load_workbook(excel_meta)
        sheet1 = wb.worksheets[0]

        if sheet1.title != self.model_id:
            raise ValueError(f"Excel sheet name '{sheet1.title}' does not match model_id '{self.model_id}'.")

        # 获取列键名
        keys = [cell.value for cell in sheet1[3]]
        seckeys = [cell.value for cell in sheet1[2]]

        # 构建关联字段映射
        asso_key_map = {}
        for idx, key in enumerate(keys):
            if idx < len(seckeys) and seckeys[idx] == "关联" and self.model_id in key:
                asso_key_map[key] = {}

        # 处理数据行
        result = []
        for row_index, row in enumerate(sheet1.iter_rows(min_row=4, min_col=1), start=4):
            item, row_has_data, row_has_errors = self._process_excel_row(row, keys, row_index, field_maps, allowed_org_set, asso_key_map)

            if row_has_data and len(item) > 1 and not row_has_errors:
                result.append(item)

        return result, asso_key_map

    def get_check_attr_map(self):
        check_attr_map = dict(is_only={}, is_required={}, editable={})
        unique_ctx = build_unique_rule_context(self.model_id)
        for attr in self.attrs:
            if attr.get(ModelConstraintKey.unique.value, False):
                check_attr_map[ModelConstraintKey.unique.value][attr["attr_id"]] = attr["attr_name"]
            if attr.get(ModelConstraintKey.required.value, False):
                check_attr_map[ModelConstraintKey.required.value][attr["attr_id"]] = attr["attr_name"]
            if attr.get(ModelConstraintKey.editable.value, True):
                check_attr_map[ModelConstraintKey.editable.value][attr["attr_id"]] = attr["attr_name"]
        check_attr_map["unique_rules"] = unique_ctx.unique_rules
        check_attr_map["attrs_by_id"] = unique_ctx.attrs_by_id
        return check_attr_map

    def _prepare_instances_for_save(self, inst_list):
        """预处理实例列表：标签规范化、字段校验、生成 _display 字段。

        Args:
            inst_list: 原始实例列表

        Returns:
            list: 处理后的实例列表
        """
        from apps.cmdb.validators import FieldValidator
        from apps.cmdb.display_field import DisplayFieldHandler

        inst_list = self._normalize_and_merge_tag_records(inst_list)

        processed_inst_list = []
        for inst_data in inst_list:
            # 1. 字段格式校验
            validation_errors = FieldValidator.validate_instance_data(inst_data, self.attrs)
            if validation_errors:
                for err in validation_errors:
                    error_msg = f"实例 {inst_data.get('inst_name', '未命名')}，字段 '{err['field_name']}'：{err['error']}"
                    self.validation_errors.append(error_msg)
                    logger.warning(error_msg)
                continue

            # 2. 生成 _display 冗余字段
            inst_data = DisplayFieldHandler.build_display_fields(self.model_id, inst_data, self.attrs)
            processed_inst_list.append(inst_data)

        return processed_inst_list

    def inst_list_save(self, inst_list):
        """实例列表保存"""
        processed_inst_list = self._prepare_instances_for_save(inst_list)

        with GraphClient() as ag:
            result = ag.batch_create_entity(
                INSTANCE,
                processed_inst_list,
                self.get_check_attr_map(),
                self.exist_items,
                self.operator,
                self.attrs,
            )
        return result

    def inst_list_update(self, inst_list):
        """实例列表更新"""
        processed_inst_list = self._prepare_instances_for_save(inst_list)

        with GraphClient() as ag:
            add_results, update_results = ag.batch_save_entity(
                INSTANCE,
                processed_inst_list,
                self.get_check_attr_map(),
                self.exist_items,
                self.operator,
                self.attrs,
            )
        return add_results, update_results

    def _normalize_and_merge_tag_records(self, records: list[dict]) -> list[dict]:
        tag_attr = next(
            (attr for attr in self.attrs if attr.get("attr_id") == TAG_ATTR_ID and attr.get("attr_type") == "tag"),
            None,
        )
        if not tag_attr:
            return records

        config = normalize_tag_field_option(tag_attr.get("option") or {})
        merged_values: set[str] = set()
        normalized_records: list[dict] = []

        for record in records:
            data = dict(record)
            if TAG_ATTR_ID in data:
                try:
                    values = normalize_tag_input_values(data.get(TAG_ATTR_ID))
                    result = validate_tag_values(values, config)
                    if result.errors:
                        raise BaseAppException("; ".join(result.errors))
                    normalized_values = [item.raw for item in result.normalized_values]
                    data[TAG_ATTR_ID] = normalized_values
                    merged_values.update(normalized_values)
                except Exception as err:
                    error_msg = f"实例 {data.get('inst_name', '未命名')}，字段 '标签'：{getattr(err, 'message', str(err))}"
                    self.validation_errors.append(error_msg)
                    logger.warning(error_msg)
                    continue

            normalized_records.append(data)

        if config.mode == TAG_MODE_FREE and merged_values:
            ModelManage.merge_tag_options_from_values(self.model_id, list(merged_values))

        return normalized_records

    def import_inst_list(self, file_stream: bytes):
        """将excel主机数据导入"""
        inst_list, _asso_key_map = self.format_excel_data(file_stream)
        result = self.inst_list_save(inst_list)
        return result

    def import_inst_list_support_edit(self, file_stream: bytes, allowed_org_ids: list = None):
        """将excel主机数据导入"""
        inst_list, asso_key_map = self.format_excel_data(file_stream, allowed_org_ids=allowed_org_ids)
        self.inst_list = inst_list
        # 执行导入（有错误的已在 format_excel_data 中被过滤）
        add_results, update_results = self.inst_list_update(inst_list)

        # 处理关联数据
        if not self.model_asso_map:
            logger.info(f"模型 {self.model_id} 没有关联模型, 无需处理关联数据")
            asso_result = []
        else:
            self.format_import_asso_data(asso_key_map)
            asso_result = self.add_asso_data(asso_key_map)

        # 将验证错误转换为失败结果（这些数据在 Excel 解析或字段校验阶段就被过滤了）
        validation_failed_results = []
        if self.validation_errors:
            logger.warning(f"数据导入过程中发现 {len(self.validation_errors)} 个验证错误，对应数据已跳过")
            for error in self.validation_errors:
                validation_failed_results.append({"success": False, "data": {}, "message": error})

        # 合并结果：验证失败 + 新增失败/成功 + 更新失败/成功
        all_add_results = validation_failed_results + add_results

        # 格式化结果消息
        self.format_import_result_message(all_add_results, update_results, asso_result)

        return all_add_results, update_results, asso_result

    def format_import_result_message(self, add_results, update_results, asso_result):
        """
        格式化导入结果消息
        :param add_results: 新增结果列表
        :param update_results: 更新结果列表
        :param asso_result: 关联数据处理结果列表
        :return: None
        """
        for item in add_results:
            inst_name = item["data"].get("inst_name", "")
            if item.get("success", False):
                # data = "实例 {} 新增成功".format(inst_name)
                data = ""
                self.import_result_message["add"]["success"] += 1
            else:
                data = "实例 {} 新增失败: {}".format(inst_name, item.get("message", "未知错误"))
                self.import_result_message["add"]["error"] += 1
            self.import_result_message["add"]["data"].append(data)

        for item in update_results:
            inst_name = item["data"].get("inst_name", "")
            if item.get("success", False):
                # data = "实例 {} 更新成功".format(inst_name)
                data = ""
                self.import_result_message["update"]["success"] += 1
            else:
                data = "实例 {} 更新失败: {}".format(inst_name, item.get("message", "未知错误"))
                self.import_result_message["update"]["error"] += 1
            self.import_result_message["update"]["data"].append(data)

        for item in asso_result:
            if item.get("success", False):
                # data = item.get("message", "关联数据处理成功")
                data = ""
                self.import_result_message["asso"]["success"] += 1
            else:
                data = item.get("message", "关联数据处理失败")
                self.import_result_message["asso"]["error"] += 1
            self.import_result_message["asso"]["data"].append(data)

    def format_import_asso_data(self, asso_key_map):
        """
        格式化关联数据
        :param asso_key_map: 关联数据键值对
        """
        if not asso_key_map:
            return

        model_asso_map = {
            i["model_asst_id"]: i["src_model_id"] if self.model_id != i["src_model_id"] else i["dst_model_id"] for i in self.model_asso_map.values()
        }

        with GraphClient() as ag:
            # 获取当前模型的实例名称与ID映射
            exist_items, _ = ag.query_entity(
                INSTANCE,
                [{"field": "model_id", "type": "str=", "value": self.model_id}],
            )
            self.inst_name_id_map[self.model_id] = {item["inst_name"]: item["_id"] for item in exist_items}
            self.inst_id_name_map[self.model_id] = {item["_id"]: item["inst_name"] for item in exist_items}

            # 获取关联模型的实例名称与ID映射
            for asso_key, inst_name_list in asso_key_map.items():
                if not inst_name_list:
                    continue
                src_model = model_asso_map[asso_key]
                exist_items, _ = ag.query_entity(
                    INSTANCE,
                    [{"field": "model_id", "type": "str=", "value": src_model}],
                )
                self.inst_name_id_map[src_model] = {item["inst_name"]: item["_id"] for item in exist_items}
                # 反转实例名称与ID映射
                self.inst_id_name_map[src_model] = {item["_id"]: item["inst_name"] for item in exist_items}

    def get_model_asso_map(self):
        """
        获取模型关联映射
        :return: 模型关联映射字典
        """

        model_asso_list = ModelManage.model_association_search(self.model_id)
        if not model_asso_list:
            return {}

        model_asso_map = {i["model_asst_id"]: i for i in model_asso_list}
        return model_asso_map

    def add_asso_data(self, asso_key_map) -> list:
        """
        添加关联数据
        :param asso_key_map: 关联数据键值对
        {
        'vmware_vm_run_vmware_esxi': {'测试2': ['10.10.16.16[host-4643]']},
        'vmware_vm_connect_vmware_ds': {'测试2': ['datastore1-16.16[datastore-4644]']}
        }
        {
            "model_asst_id": "vmware_vm_connect_vmware_ds",
            "src_model_id": "vmware_vm", # 源模型
            "dst_model_id": "vmware_ds", # 目标模型
            "asst_id": "connect",
            "src_inst_id": 156,
            "dst_inst_id": 144
        }
        """
        if not asso_key_map:
            return []

        add_asso_list = []

        for asso_key, inst_name_list in asso_key_map.items():
            if not inst_name_list:
                continue
            if asso_key not in self.model_asso_map:
                continue
            asso_info = self.model_asso_map[asso_key]
            asst_id = asso_info["asst_id"]
            src_model_id = asso_info["src_model_id"]
            dst_model_id = asso_info["dst_model_id"]

            for _model_src_inst_name, _dst_inst_name_list in inst_name_list.items():
                # 导入模型的实例名称的ID 源ID
                import_model_inst_name_id = self.inst_name_id_map[self.model_id].get(_model_src_inst_name)
                if not import_model_inst_name_id:
                    continue
                # 目标模型ID
                _dst_inst_model_id = dst_model_id if self.model_id == src_model_id else src_model_id

                for dst_inst_name in _dst_inst_name_list:
                    # 目标模型的实例名称的ID
                    _dst_inst_id = self.inst_name_id_map[_dst_inst_model_id].get(dst_inst_name)
                    if not _dst_inst_id:
                        continue
                    if self.model_id == src_model_id:
                        src_inst_id = import_model_inst_name_id
                        dst_inst_id = _dst_inst_id
                    else:
                        src_inst_id = _dst_inst_id
                        dst_inst_id = import_model_inst_name_id

                    add_asso_list.append(
                        dict(
                            model_asst_id=asso_key,
                            src_model_id=src_model_id,
                            dst_model_id=dst_model_id,
                            asst_id=asst_id,
                            src_inst_id=src_inst_id,
                            dst_inst_id=dst_inst_id,
                        )
                    )

        if not add_asso_list:
            return []

        result = []
        for add_asso in add_asso_list:
            try:
                asso = self.instance_association_create(add_asso, operator=self.operator)
            except Exception as err:
                asso = {"success": False, "message": "创建关联失败: {}".format(err)}
            result.append(asso)
        return result

    def instance_association_create(self, data: dict, operator: str):
        """创建实例关联"""

        # 校验关联约束
        model_asst_id = data["model_asst_id"]
        src_inst_name = self.inst_id_name_map[data["src_model_id"]][data["src_inst_id"]]
        dst_inst_name = self.inst_id_name_map[data["dst_model_id"]][data["dst_inst_id"]]

        try:
            from apps.cmdb.services.instance import InstanceManage

            InstanceManage.check_asso_mapping(data)
        except Exception as err:
            import traceback

            logger.error("校验关联约束失败: {}".format(traceback.format_exc()))
            return {
                "success": False,
                "message": "【{}】与【{}】的关联关系【{}】创建失败！校验关联约束失败! ".format(src_inst_name, dst_inst_name, model_asst_id),
            }

        with GraphClient() as ag:
            try:
                edge = ag.create_edge(
                    INSTANCE_ASSOCIATION,
                    data["src_inst_id"],
                    INSTANCE,
                    data["dst_inst_id"],
                    INSTANCE,
                    data,
                    "model_asst_id",
                )
            except BaseAppException as e:
                if e.message == "edge already exists":
                    message = "关联 【{}】与【{}】的关联关系【{}】 已存在".format(src_inst_name, dst_inst_name, model_asst_id)
                else:
                    message = "【{}】与【{}】的关联关系【{}】创建失败！".format(src_inst_name, dst_inst_name, model_asst_id)
                return {"success": False, "message": message}

        asso_info = InstanceManage.instance_association_by_asso_id(edge["_id"])
        message = f"创建模型关联关系. 原模型: {asso_info['src']['model_id']} 原模型实例: {asso_info['src']['inst_name']}  目标模型ID: {asso_info['dst']['model_id']} 目标模型实例: {asso_info['dst'].get('inst_name') or asso_info['dst'].get('ip_addr', '')}"
        create_change_record_by_asso(
            INSTANCE_ASSOCIATION,
            CREATE_INST_ASST,
            asso_info,
            message=message,
            operator=operator,
        )

        return {
            "success": True,
            "data": edge,
            "message": "【{}】与【{}】的关联关系【{}】创建成功".format(src_inst_name, dst_inst_name, model_asst_id),
        }
