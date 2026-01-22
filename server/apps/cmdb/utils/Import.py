import ast

import openpyxl

from apps.cmdb.constants.constants import INSTANCE, NEED_CONVERSION_TYPE, ORGANIZATION, USER, ENUM, \
    INSTANCE_ASSOCIATION, ModelConstraintKey
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models import CREATE_INST_ASST
from apps.cmdb.services.model import ModelManage
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
        self.import_result_message = {"add": {"success": 0, "error": 0, "data": []},
                                      "update": {"success": 0, "error": 0, "data": []},
                                      "asso": {"success": 0, "error": 0, "data": []}}
        self.model_asso_map = self.get_model_asso_map()
        # 用于收集数据验证错误
        self.validation_errors = []

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

    def _resolve_organization_ids(self, value_list: list, allowed_org_set: set, row_index: int, field_display_name: str):
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
            parent_name_map = {
                r["id"]: r["name"] for r in Group.objects.filter(id__in=parent_ids).values("id", "name")
            }

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
                    candidates = [
                        c for c in candidates if parent_name_map.get(c.get("parent_id")) == parent_name
                    ]

                if not candidates:
                    invalid_values.append(raw)
                    continue

                if allowed_org_set is None:
                    return [], f"第{row_index}行，字段'{field_display_name}'缺少组织范围上下文，请刷新后重试", organization_cell_provided

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
            return [], f"第{row_index}行，字段'{field_display_name}'的值'{invalid_values}'无效", organization_cell_provided

        if out_of_scope_values:
            return [], f"第{row_index}行，字段'{field_display_name}'的值'{out_of_scope_values}'不在当前选择组织范围内", organization_cell_provided

        return enum_id, None, organization_cell_provided

    def format_excel_data(self, excel_meta: bytes, allowed_org_ids: list = None):
        """格式化excel"""

        allowed_org_set = set(allowed_org_ids) if allowed_org_ids is not None else None

        need_val_to_id_field_map, need_update_type_field_map, org_user_map = {}, {}, {}
        # 创建属性名称映射，用于错误提示
        attr_name_map = {attr_info["attr_id"]: attr_info["attr_name"] for attr_info in self.attrs}

        for attr_info in self.attrs:
            if attr_info["attr_type"] in NEED_CONVERSION_TYPE:
                need_update_type_field_map[attr_info["attr_id"]] = attr_info["attr_type"]
                continue

            if attr_info["attr_type"] in {ORGANIZATION, USER, ENUM}:
                need_val_to_id_field_map[attr_info["attr_id"]] = {i["name"]: i["id"] for i in attr_info["option"]}
                if attr_info["attr_type"] in {ORGANIZATION, USER}:
                    org_user_map[attr_info["attr_id"]] = attr_info["attr_type"]
        # 读取临时文件
        wb = openpyxl.load_workbook(excel_meta)
        # 获取第一个工作表
        sheet1 = wb.worksheets[0]
        # 获取工作表名称 就是模型名称
        if sheet1.title != self.model_id:
            raise ValueError(f"Excel sheet name '{sheet1.title}' does not match model_id '{self.model_id}'.")

        # 获取键
        keys = [cell.value for cell in sheet1[3]]  # 3
        # 中文键值
        seckeys = [cell.value for cell in sheet1[2]]  # 3
        asso_key_map = {}
        # asso_key_map = {i: {} for i in keys if self.model_id in i}
        for idx, key in enumerate(keys):
            if idx < len(seckeys) and seckeys[idx] == "关联" and self.model_id in key:
                asso_key_map[key] = {}
        result = []
        # 从第4行第1列开始遍历
        for row_index, row in enumerate(sheet1.iter_rows(min_row=4, min_col=1), start=4):
            # 创建字典
            item = {"model_id": self.model_id}
            inst_name = ""
            row_has_data = False
            organization_cell_provided = False
            row_validation_errors_count = len(self.validation_errors)  # 记录处理该行前的错误数量

            # 遍历每一列
            for i, cell in enumerate(row):
                try:
                    value = ast.literal_eval(cell.value)
                except Exception:
                    value = cell.value

                if not value:
                    continue

                row_has_data = True

                if keys[i] == ORGANIZATION:
                    organization_cell_provided = True

                if keys[i] == "inst_name":
                    inst_name = value

                if keys[i] in asso_key_map:
                    # 处理关联字段
                    if not inst_name:
                        continue
                    split_value = value.split(",")
                    asso_key_map[keys[i]].setdefault(inst_name, []).extend(split_value)
                    continue

                # 将需要类型转换的键和值存入字典
                if keys[i] in need_update_type_field_map:
                    try:
                        method = NEED_CONVERSION_TYPE[need_update_type_field_map[keys[i]]]
                        item[keys[i]] = method(value)
                    except (ValueError, TypeError) as e:
                        error_msg = f"第{row_index}行，字段'{attr_name_map.get(keys[i], keys[i])}'的值'{value}'格式错误"
                        self.validation_errors.append(error_msg)
                        logger.warning(error_msg)
                    continue

                # 将需要枚举字段name与id反转的建和值存入字典
                if keys[i] in need_val_to_id_field_map:
                    if keys[i] in org_user_map:
                        if type(value) != list:
                            if ',' in str(value):
                                value_list = str(value).split(',')
                            elif '，' in str(value):
                                value_list = str(value).split('，')
                            else:
                                value_list = [str(value)]
                        else:
                            value_list = value

                        # 组织字段：支持 Default/xxx，并做范围校验
                        if org_user_map[keys[i]] == ORGANIZATION:
                            org_ids, error_msg, provided = self._resolve_organization_ids(
                                value_list=value_list,
                                allowed_org_set=allowed_org_set,
                                row_index=row_index,
                                field_display_name=attr_name_map.get(keys[i], keys[i]),
                            )
                            organization_cell_provided = organization_cell_provided or provided

                            if error_msg:
                                self.validation_errors.append(error_msg)
                                logger.warning(error_msg)
                                continue

                            if org_ids:
                                item[keys[i]] = org_ids
                            continue

                        enum_id = []
                        invalid_values = []
                        for val in value_list:
                            raw_val = val
                            lookup_val = self._normalize_user_token(val) if org_user_map[keys[i]] == USER else val
                            mapped_id = need_val_to_id_field_map[keys[i]].get(lookup_val)
                            if mapped_id is not None:
                                enum_id.append(mapped_id)
                            else:
                                invalid_values.append(raw_val)

                        # 用户字段：主要维护人(operator)支持多选；其他USER字段保持原先单选逻辑
                        if org_user_map[keys[i]] == USER:
                            if keys[i] == "operator":
                                # 允许多个主要维护人：保存为list；单个则保持标量，兼容旧数据
                                if len(enum_id) == 1:
                                    enum_id = enum_id[0]
                                elif len(enum_id) > 1:
                                    enum_id = enum_id
                            else:
                                if len(enum_id) >= 1:
                                    enum_id = enum_id[0]
                        if invalid_values:
                            logger.warning(need_val_to_id_field_map[keys[i]])
                            error_msg = f"第{row_index}行，字段'{attr_name_map.get(keys[i], keys[i])}'的值'{invalid_values}'无效"
                            self.validation_errors.append(error_msg)
                            logger.warning(error_msg)

                        # 只有当没有验证错误时才设置字段值
                        if enum_id and not invalid_values:
                            item[keys[i]] = enum_id
                    else:
                        enum_id = need_val_to_id_field_map[keys[i]].get(value)
                        if enum_id is not None:
                            item[keys[i]] = enum_id
                        else:
                            error_msg = f"第{row_index}行，字段'{attr_name_map.get(keys[i], keys[i])}'的值'{value}'无效"
                            self.validation_errors.append(error_msg)
                            logger.warning(error_msg)
                    continue

                # 将键和值存入字典
                item[keys[i]] = value
            # 检查该行是否有验证错误
            row_has_validation_errors = len(self.validation_errors) > row_validation_errors_count

            # 只有当行有数据且没有验证错误时才添加到结果列表
            if row_has_data and len(item) > 1 and not row_has_validation_errors:
                result.append(item)
                print(item)
        return result, asso_key_map

    def get_check_attr_map(self):
        check_attr_map = dict(is_only={}, is_required={}, editable={})
        for attr in self.attrs:
            if attr[ModelConstraintKey.unique.value]:
                check_attr_map[ModelConstraintKey.unique.value][attr["attr_id"]] = attr["attr_name"]
            if attr[ModelConstraintKey.required.value]:
                check_attr_map[ModelConstraintKey.required.value][attr["attr_id"]] = attr["attr_name"]
            if attr[ModelConstraintKey.editable.value]:
                check_attr_map[ModelConstraintKey.editable.value][attr["attr_id"]] = attr["attr_name"]
        return check_attr_map

    def inst_list_save(self, inst_list):
        """实例列表保存"""

        for item in inst_list or []:
            if isinstance(item, dict) and "cloud" in item and item.get("cloud") is not None:
                item["cloud"] = str(item.get("cloud"))

        with GraphClient() as ag:
            result = ag.batch_create_entity(INSTANCE, inst_list, self.get_check_attr_map(), self.exist_items,
                                            self.operator)
        return result

    def inst_list_update(self, inst_list):
        """实例列表更新"""

        for item in inst_list or []:
            if isinstance(item, dict) and "cloud" in item and item.get("cloud") is not None:
                item["cloud"] = str(item.get("cloud"))

        with GraphClient() as ag:
            add_results, update_results = ag.batch_save_entity(INSTANCE, inst_list, self.get_check_attr_map(),
                                                               self.exist_items, self.operator)
        return add_results, update_results

    def import_inst_list(self, file_stream: bytes):
        """将excel主机数据导入"""
        inst_list, _asso_key_map = self.format_excel_data(file_stream)
        result = self.inst_list_save(inst_list)
        return result

    def import_inst_list_support_edit(self, file_stream: bytes, allowed_org_ids: list = None):
        """将excel主机数据导入"""
        inst_list, asso_key_map = self.format_excel_data(file_stream, allowed_org_ids=allowed_org_ids)

        # 如果存在验证错误，立即返回错误信息，不执行导入
        if self.validation_errors:
            logger.error(f"数据导入验证失败，共发现 {len(self.validation_errors)} 个错误")
            error_result = []
            for error in self.validation_errors:
                error_result.append({"success": False, "data": {}, "message": error})
            return error_result, [], []

        add_results, update_results = self.inst_list_update(inst_list)
        if not self.model_asso_map:
            logger.info(f"模型 {self.model_id} 没有关联模型, 无需处理关联数据")
            self.format_import_result_message(add_results, update_results, [])
            return add_results, update_results, []
        self.format_import_asso_data(asso_key_map)
        asso_result = self.add_asso_data(asso_key_map)
        self.format_import_result_message(add_results, update_results, asso_result)
        return add_results, update_results, asso_result

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
                data = "实例 {} 新增成功".format(inst_name)
                self.import_result_message["add"]["success"] += 1
            else:
                data = "实例 {} 新增失败: {}".format(inst_name, item.get("message", "未知错误"))
                self.import_result_message["add"]["error"] += 1
            self.import_result_message["add"]["data"].append(data)

        for item in update_results:
            inst_name = item["data"].get("inst_name", "")
            if item.get("success", False):
                data = "实例 {} 更新成功".format(inst_name)
                self.import_result_message["update"]["success"] += 1
            else:
                data = "实例 {} 更新失败: {}".format(inst_name, item.get("message", "未知错误"))
                self.import_result_message["update"]["error"] += 1
            self.import_result_message["update"]["data"].append(data)

        for item in asso_result:
            if item.get("success", False):
                data = item.get("message", "关联数据处理成功")
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
            i["model_asst_id"]: i["src_model_id"] if self.model_id != i["src_model_id"] else i["dst_model_id"] for i in
            self.model_asso_map.values()}

        with GraphClient() as ag:
            # 获取当前模型的实例名称与ID映射
            exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": self.model_id}])
            self.inst_name_id_map[self.model_id] = {item["inst_name"]: item["_id"] for item in exist_items}
            self.inst_id_name_map[self.model_id] = {item["_id"]: item["inst_name"] for item in exist_items}

            # 获取关联模型的实例名称与ID映射
            for asso_key, inst_name_list in asso_key_map.items():
                if not inst_name_list:
                    continue
                src_model = model_asso_map[asso_key]
                exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": src_model}])
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
                            dst_inst_id=dst_inst_id
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
            return {"success": False,
                    "message": "【{}】与【{}】的关联关系【{}】创建失败！校验关联约束失败! ".format(src_inst_name,
                                                                                            dst_inst_name,
                                                                                            model_asst_id)}

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
        create_change_record_by_asso(INSTANCE_ASSOCIATION, CREATE_INST_ASST, asso_info, message=message,
                                     operator=operator)

        return {"success": True, "data": edge,
                "message": "【{}】与【{}】的关联关系【{}】创建成功".format(src_inst_name, dst_inst_name, model_asst_id)}
