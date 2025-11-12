import ast
import json

import pandas as pd

from apps.cmdb.constants import (
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
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.utils.base import get_default_group_id
from apps.core.logger import cmdb_logger as logger


class ModelMigrate:
    def __init__(self):
        self.model_config = self.get_model_config()
        self.default_group_id = get_default_group_id()

    def get_model_config(self):
        # 读取 Excel 文件
        file_path = "apps/cmdb/model_migrate/model_config.xlsx"

        # 指定第二行（索引1）作为表头，并读取所有 sheet 页
        sheets_dict = pd.read_excel(file_path, sheet_name=None, header=1)

        sheets_map = {}

        # 遍历所有 sheet 页，并将每个 sheet 页的 DataFrame 转换为列表字典
        for sheet_name, sheet_data in sheets_dict.items():
            # 对 NaN 值进行填充，修改原 DataFrame
            sheet_data.fillna("", inplace=True)

            # 如果 sheet_data 是 Series（单列数据），转换为 DataFrame
            if isinstance(sheet_data, pd.Series):
                sheet_data = sheet_data.to_frame()  # 将 Series 转换为 DataFrame

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

    def migrate_models(self):
        """初始化模型"""
        models = []
        for model in self.model_config.get("models", []):
            model.update(is_pre=True)
            self.model_add_organization(model)
            _attrs = []
            attr_key = f"attr-{model['model_id']}"
            attrs = self.model_config.get(attr_key, [])
            for attr in attrs:
                attr.update(is_pre=True)
                try:
                    attr["option"] = ast.literal_eval(attr["option"])
                except Exception:
                    pass
                # 过滤掉关键字段为空的行
                if not attr["attr_id"]:
                    continue
                _attrs.append(attr)
            models.append({**model, "attrs": json.dumps(_attrs)})

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(MODEL, [])
            exist_classifications, _ = ag.query_entity(CLASSIFICATION, [])
            classification_map = {i["classification_id"]: i["_id"] for i in exist_classifications}
            models = [i for i in models if i.get("classification_id") in classification_map]
            result = ag.batch_create_entity(MODEL, models, CREATE_MODEL_CHECK_ATTR, exist_items)

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
                SUBORDINATE_MODEL, CLASSIFICATION, MODEL, asso_list, "classification_model_asst_id"
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
            result = ag.batch_create_edge(MODEL_ASSOCIATION, MODEL, MODEL, asso_list, "model_asst_id")
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
            logger.error(f"Error updating old instances organization: {traceback.format_exc()}")

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
                elif INIT_MODEL_GROUP in model and isinstance(model[INIT_MODEL_GROUP], int):
                    # 如果组织字段是单个整数，转换为列表
                    models_without_group.append(model["_id"])

            # 批量更新缺少组织字段的模型
            if models_without_group:
                ag.batch_update_node_properties(
                    label=MODEL,
                    node_ids=models_without_group,
                    properties={INIT_MODEL_GROUP: self.default_group_id}
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
                    properties={ORGANIZATION: self.default_group_id}
                )
                logger.info(f"Successfully updated {len(instances_need_fix)} instances organization field to list type")
