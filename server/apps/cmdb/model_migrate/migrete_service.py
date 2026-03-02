import ast
import json

import pandas as pd

from apps.cmdb.constants.constants import (
    CLASSIFICATION,
    CREATE_CLASSIFICATION_CHECK_ATTR_MAP,
    CREATE_MODEL_CHECK_ATTR,
    INSTANCE,
    MODEL,
    MODEL_ASSOCIATION,
    ORGANIZATION,
    SUBORDINATE_MODEL,
    INIT_MODEL_GROUP,
)
from apps.cmdb.constants.field_constraints import (
    DEFAULT_NUMBER_CONSTRAINT,
    DEFAULT_STRING_CONSTRAINT,
    DEFAULT_TIME_CONSTRAINT,
    StringValidationType,
    TimeDisplayFormat,
    WidgetType,
)
from apps.cmdb.validators import IdentifierValidator
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.utils.base import get_default_group_id
from apps.core.logger import cmdb_logger as logger


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
    def __init__(self):
        self.model_config = self.get_model_config()
        self.default_group_id = get_default_group_id()

    def get_model_config(self):
        # 读取 Excel 文件
        file_path = "apps/cmdb/support-files/model_config.xlsx"

        # 指定第二行（索引1）作为表头，并读取所有 sheet 页
        sheets_dict = pd.read_excel(file_path, sheet_name=None, header=1)

        sheets_map = {}

        # 遍历所有 sheet 页，并将每个 sheet 页的 DataFrame 转换为列表字典
        for sheet_name, sheet_data in sheets_dict.items():
            # 如果 sheet_data 是 Series（单列数据），转换为 DataFrame
            if isinstance(sheet_data, pd.Series):
                sheet_data = sheet_data.to_frame()  # 将 Series 转换为 DataFrame

            # 对 NaN 值进行填充，先转换为 object 类型避免类型不兼容警告
            sheet_data = sheet_data.astype(object).fillna("")

            # 将 DataFrame 转换为字典格式，使用 'records' 使每行成为一个字典
            data = sheet_data.to_dict(orient="records")

            sheets_map[sheet_name] = data

        return sheets_map

    def migrate_classifications(self):
        """初始化模型分类"""

        for classification in self.model_config.get("classifications", []):
            classification.update(is_pre=True)

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(CLASSIFICATION, [])
            result = ag.batch_create_entity(
                CLASSIFICATION,
                self.model_config.get("classifications", []),
                CREATE_CLASSIFICATION_CHECK_ATTR_MAP,
                exist_items,
            )
        return result

    def model_add_organization(self, model):
        """
        给模型添加组织数据
        """
        _key = INIT_MODEL_GROUP
        model[_key] = self.default_group_id

    def _parse_attr_option(self, attr_type: str, option_value) -> dict:
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
            return parsed if isinstance(parsed, list) else []
        elif attr_type == "table":
            return self._parse_table_option(parsed)

        return parsed if isinstance(parsed, dict) else {}

    def _get_default_option(self, attr_type: str) -> dict:
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
            validation_type = EXCEL_STR_TYPE_MAP.get(
                type_value, StringValidationType.UNRESTRICTED
            )
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
        result = DEFAULT_NUMBER_CONSTRAINT.copy()

        min_val = parsed.get("min")
        if min_val is not None and min_val != "":
            try:
                result["min_value"] = (
                    float(min_val) if "." in str(min_val) else int(min_val)
                )
            except (ValueError, TypeError):
                pass

        max_val = parsed.get("max")
        if max_val is not None and max_val != "":
            try:
                result["max_value"] = (
                    float(max_val) if "." in str(max_val) else int(max_val)
                )
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
                order_int = int(order)
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

    def migrate_models(self):
        """初始化模型"""
        models = []
        for model in self.model_config.get("models", []):
            model_id = model.get("model_id", "")
            if not IdentifierValidator.is_valid(model_id):
                logger.warning(f"跳过无效模型ID: {model_id}")
                continue

            model.update(is_pre=True)
            self.model_add_organization(model)
            _attrs = []
            attr_key = f"attr-{model_id}"
            attrs = self.model_config.get(attr_key, [])
            for attr in attrs:
                attr.update(is_pre=True)

                if not attr.get("attr_id"):
                    continue

                attr_type = attr.get("attr_type", "str")
                option_value = attr.get("option", "")
                attr["option"] = self._parse_attr_option(attr_type, option_value)

                user_prompt = attr.get("prompt", "") or attr.get("user_prompt", "")
                attr["user_prompt"] = str(user_prompt) if user_prompt else ""

                _attrs.append(attr)
            models.append({**model, "attrs": json.dumps(_attrs)})

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(MODEL, [])
            exist_classifications, _ = ag.query_entity(CLASSIFICATION, [])
            classification_map = {
                i["classification_id"]: i["_id"] for i in exist_classifications
            }
            models = [
                i for i in models if i.get("classification_id") in classification_map
            ]
            result = ag.batch_create_entity(
                MODEL, models, CREATE_MODEL_CHECK_ATTR, exist_items
            )

            success_models = [i["data"] for i in result if i["success"]]
            asso_list = [
                dict(
                    src_id=classification_map[i["classification_id"]],
                    dst_id=i["_id"],
                    classification_model_asst_id=f"{i['classification_id']}_{SUBORDINATE_MODEL}_{i['model_id']}",
                )
                for i in success_models
            ]
            asso_result = ag.batch_create_edge(
                SUBORDINATE_MODEL,
                CLASSIFICATION,
                MODEL,
                asso_list,
                "classification_model_asst_id",
            )

        return result, asso_result

    def migrate_associations(self):
        """初始模型关联"""
        associations = []
        for model in self.model_config.get("models", []):
            asso_key = f"asso-{model['model_id']}"
            if asso_key in self.model_config:
                associations.extend(self.model_config[asso_key])

        for association in associations:
            association.update(is_pre=True)

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
            ]
            result = ag.batch_create_edge(
                MODEL_ASSOCIATION, MODEL, MODEL, asso_list, "model_asst_id"
            )
        return result

    def main(self):
        # 创建模型分类
        classification_resp = self.migrate_classifications()
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

            logger.error(
                f"Error updating old instances organization: {traceback.format_exc()}"
            )

        return dict(
            classification=classification_resp,
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
                elif INIT_MODEL_GROUP in model and isinstance(
                    model[INIT_MODEL_GROUP], int
                ):
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
                logger.info(
                    f"Found {len(instances_need_fix)} instances with incorrect organization field type"
                )
                ag.batch_update_node_properties(
                    label=INSTANCE,
                    node_ids=instances_need_fix,
                    properties={ORGANIZATION: self.default_group_id},
                )
                logger.info(
                    f"Successfully updated {len(instances_need_fix)} instances organization field to list type"
                )
