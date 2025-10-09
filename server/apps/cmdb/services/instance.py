from apps.cmdb.constants import INSTANCE, INSTANCE_ASSOCIATION, OPERATOR_INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.change_record import CREATE_INST, CREATE_INST_ASST, DELETE_INST, DELETE_INST_ASST, UPDATE_INST
from apps.cmdb.models.show_field import ShowField
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.change_record import batch_create_change_record, create_change_record, create_change_record_by_asso
from apps.cmdb.utils.export import Export
from apps.cmdb.utils.Import import Import
from apps.cmdb.utils.permission import PermissionManage
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


class InstanceManage(object):

    @classmethod
    def search_inst(cls, model_id: str, inst_name: str = None, _id: int = None):
        """查询实例"""
        with GraphClient() as ag:
            params = [{"field": "model_id", "type": "str=", "value": model_id}]
            if _id:
                params.append({"field": "id", "type": "id=", "value": int(_id)})
            if inst_name:
                params.append({"field": "inst_name", "type": "str=", "value": inst_name})
            inst_list, count = ag.query_entity(INSTANCE, params)
        return inst_list, count

    @staticmethod
    def get_permission_params(user_groups, roles):
        """获取用户实例权限查询参数，用户用户查询实例"""
        obj = PermissionManage(user_groups=user_groups, roles=roles)
        permission_params = obj.get_permission_params()
        return permission_params

    @staticmethod
    def check_instances_permission(user_groups: list, roles: list, instances: list, model_id: str):
        """实例权限校验，用于操作之前"""
        permission_params = InstanceManage.get_permission_params(user_groups=user_groups, roles=roles)
        with GraphClient() as ag:
            inst_list, count = ag.query_entity(
                INSTANCE,
                [{"field": "model_id", "type": "str=", "value": model_id}],
                permission_params=permission_params,
            )

        permission_map = {i["_id"]: i for i in inst_list}
        instances_map = {i["_id"]: i for i in instances}

        non_permission_set = set(instances_map.keys()) - set(permission_map.keys())

        if not non_permission_set:
            return
        message = f"实例：{'、'.join([instances_map[i]['inst_name'] for i in non_permission_set])}，无权限！"
        raise BaseAppException(message)

    @staticmethod
    def instance_list(user_groups: list, roles: list, model_id: str, params: list, page: int, page_size: int,
                      order: str, inst_names: list = [], check_permission=True, creator: str = None):
        """实例列表"""

        params.append({"field": "model_id", "type": "str=", "value": model_id})

        # 构建权限过滤条件：有权限的实例 OR 自己创建的实例
        permission_or_creator_filter = None
        if inst_names:
            # 既有实例名称权限限制，又有创建人条件，构建OR条件
            permission_or_creator_filter = {"inst_names": inst_names}
        elif creator:
            # 只有创建人条件
            params.append({"field": "_creator", "type": "str=", "value": creator})

        _page = dict(skip=(page - 1) * page_size, limit=page_size)
        if order and order.startswith("-"):
            order = f"{order.replace('-', '')} DESC"
        if not check_permission:
            permission_params = ""
        else:
            permission_params = InstanceManage.get_permission_params(user_groups, roles)

        with GraphClient() as ag:
            inst_list, count = ag.query_entity(
                INSTANCE,
                params,
                page=_page,
                order=order,
                permission_params=permission_params,
                permission_or_creator_filter=permission_or_creator_filter,
            )

        return inst_list, count

    @staticmethod
    def instance_create(model_id: str, instance_info: dict, operator: str):
        """创建实例"""
        instance_info.update(model_id=model_id)
        attrs = ModelManage.search_model_attr(model_id)
        check_attr_map = dict(is_only={}, is_required={})
        for attr in attrs:
            if attr["is_only"]:
                check_attr_map["is_only"][attr["attr_id"]] = attr["attr_name"]
            if attr["is_required"]:
                check_attr_map["is_required"][attr["attr_id"]] = attr["attr_name"]

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
            result = ag.create_entity(INSTANCE, instance_info, check_attr_map, exist_items, operator)

        create_change_record(
            result["_id"],
            result["model_id"],
            INSTANCE,
            CREATE_INST,
            after_data=result,
            operator=operator,
            model_object=OPERATOR_INSTANCE,
            message=f"创建模型实例. 模型:{result['model_id']} 实例:{result.get('inst_name') or result.get('ip_addr', '')}",
        )
        return result

    @staticmethod
    def instance_update(user_groups: list, roles: list, inst_id: int, update_attr: dict, operator: str):
        """修改实例属性"""
        inst_info = InstanceManage.query_entity_by_id(inst_id)

        if not inst_info:
            raise BaseAppException("实例不存在！")

        model_info = ModelManage.search_model_info(inst_info["model_id"])

        InstanceManage.check_instances_permission(user_groups, roles, [inst_info], inst_info["model_id"])

        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
        check_attr_map = dict(is_only={}, is_required={}, editable={})
        for attr in attrs:
            if attr["is_only"]:
                check_attr_map["is_only"][attr["attr_id"]] = attr["attr_name"]
            if attr["is_required"]:
                check_attr_map["is_required"][attr["attr_id"]] = attr["attr_name"]
            if attr["editable"]:
                check_attr_map["editable"][attr["attr_id"]] = attr["attr_name"]

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(
                INSTANCE,
                [{"field": "model_id", "type": "str=", "value": inst_info["model_id"]}],
            )
            exist_items = [i for i in exist_items if i["_id"] != inst_id]
            result = ag.set_entity_properties(INSTANCE, [inst_id], update_attr, check_attr_map, exist_items)

        create_change_record(
            inst_info["_id"],
            inst_info["model_id"],
            INSTANCE,
            UPDATE_INST,
            before_data=inst_info,
            after_data=result[0],
            operator=operator,
            model_object=OPERATOR_INSTANCE,
            message=f"修改模型实例属性. 模型:{model_info['model_name']} 实例:{result[0]['inst_name']}",
        )

        return result[0]

    @staticmethod
    def batch_instance_update(user_groups: list, roles: list, inst_ids: list, update_attr: dict, operator: str):
        """批量修改实例属性"""

        inst_list = InstanceManage.query_entity_by_ids(inst_ids)

        if not inst_list:
            raise BaseAppException("实例不存在！")

        model_info = ModelManage.search_model_info(inst_list[0]["model_id"])

        InstanceManage.check_instances_permission(user_groups, roles, inst_list, model_info["model_id"])

        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
        check_attr_map = dict(is_only={}, is_required={}, editable={})
        for attr in attrs:
            if attr["is_only"]:
                check_attr_map["is_only"][attr["attr_id"]] = attr["attr_name"]
            if attr["is_required"]:
                check_attr_map["is_required"][attr["attr_id"]] = attr["attr_name"]
            if attr["editable"]:
                check_attr_map["editable"][attr["attr_id"]] = attr["attr_name"]

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(
                INSTANCE,
                [
                    {
                        "field": "model_id",
                        "type": "str=",
                        "value": model_info["model_id"],
                    }
                ],
            )
            exist_items = [i for i in exist_items if i["_id"] not in inst_ids]
            result = ag.set_entity_properties(INSTANCE, inst_ids, update_attr, check_attr_map, exist_items)

        after_dict = {i["_id"]: i for i in result}
        change_records = [
            dict(
                inst_id=i["_id"],
                model_id=i["model_id"],
                before_data=i,
                after_data=after_dict.get(i["_id"]),
                model_object=OPERATOR_INSTANCE,
                message=f"修改模型实例属性. 模型:{model_info['model_name']} 实例:{i.get('inst_name') or i.get('ip_addr', '')}",
            )
            for i in inst_list
        ]
        batch_create_change_record(INSTANCE, UPDATE_INST, change_records, operator=operator)

        return result

    @staticmethod
    def instance_batch_delete(user_groups: list, roles: list, inst_ids: list, operator: str):
        """批量删除实例"""
        inst_list = InstanceManage.query_entity_by_ids(inst_ids)

        if not inst_list:
            raise BaseAppException("实例不存在！")

        model_info = ModelManage.search_model_info(inst_list[0]["model_id"])

        InstanceManage.check_instances_permission(user_groups, roles, inst_list, inst_list[0]["model_id"])

        with GraphClient() as ag:
            ag.batch_delete_entity(INSTANCE, inst_ids)

        change_records = [dict(inst_id=i["_id"], model_id=i["model_id"], before_data=i, model_object=OPERATOR_INSTANCE,
                               message=f"删除模型实例. 模型:{model_info['model_name']} 实例:{i.get('inst_name') or i.get('ip_addr', '')}")
                          for i in inst_list]
        batch_create_change_record(INSTANCE, DELETE_INST, change_records, operator=operator)

    @staticmethod
    def instance_association_instance_list(model_id: str, inst_id: int):
        """查询模型实例关联的实例列表"""

        with GraphClient() as ag:
            # 作为源模型实例
            src_query_data = [
                {"field": "src_inst_id", "type": "int=", "value": inst_id},
                {"field": "src_model_id", "type": "str=", "value": model_id},
            ]
            src_edge = ag.query_edge(INSTANCE_ASSOCIATION, src_query_data, return_entity=True)

            # 作为目标模型实例
            dst_query_data = [
                {"field": "dst_inst_id", "type": "int=", "value": inst_id},
                {"field": "dst_model_id", "type": "str=", "value": model_id},
            ]
            dst_edge = ag.query_edge(INSTANCE_ASSOCIATION, dst_query_data, return_entity=True)

        result = {}
        for item in src_edge + dst_edge:
            model_asst_id = item["edge"]["model_asst_id"]
            item_key = "src" if model_id == item["edge"]["dst_model_id"] else "dst"
            if model_asst_id not in result:
                result[model_asst_id] = {
                    "src_model_id": item["edge"]["src_model_id"],
                    "dst_model_id": item["edge"]["dst_model_id"],
                    "model_asst_id": item["edge"]["model_asst_id"],
                    "asst_id": item["edge"].get("asst_id"),
                    "inst_list": [],
                }
            item[item_key].update(inst_asst_id=item["edge"]["_id"])
            result[model_asst_id]["inst_list"].append(item[item_key])

        return list(result.values())

    @staticmethod
    def instance_association(model_id: str, inst_id: int):
        """查询模型实例关联的实例列表"""

        with GraphClient() as ag:
            # 作为源模型实例
            src_query_data = [
                {"field": "src_inst_id", "type": "int=", "value": inst_id},
                {"field": "src_model_id", "type": "str=", "value": model_id},
            ]
            src_edge = ag.query_edge(INSTANCE_ASSOCIATION, src_query_data)

            # 作为目标模型实例
            dst_query_data = [
                {"field": "dst_inst_id", "type": "int=", "value": inst_id},
                {"field": "dst_model_id", "type": "str=", "value": model_id},
            ]
            dst_edge = ag.query_edge(INSTANCE_ASSOCIATION, dst_query_data)

        return src_edge + dst_edge

    @staticmethod
    def check_asso_mapping(data: dict):
        """校验关联关系的约束"""
        asso_info = ModelManage.model_association_info_search(data["model_asst_id"])
        if not asso_info:
            raise BaseAppException("association not found!")

        # n:n关联不做校验
        if asso_info["mapping"] == "n:n":
            return

        # 1:n关联校验
        elif asso_info["mapping"] == "1:n":
            # 检查目标实例是否已经存在关联
            with GraphClient() as ag:
                # 作为源模型实例
                dst_query_data = [
                    {"field": "dst_inst_id", "type": "int=", "value": data["dst_inst_id"]},
                    {"field": "model_asst_id", "type": "str=", "value": data["model_asst_id"]},
                ]
                dst_edge = ag.query_edge(INSTANCE_ASSOCIATION, dst_query_data)
                if dst_edge:
                    raise BaseAppException("destination instance already exists association!")
        # n:1关联校验
        elif asso_info["mapping"] == "n:1":
            # 检查源实例是否已经存在关联
            with GraphClient() as ag:
                src_query_data = [
                    {"field": "src_inst_id", "type": "int=", "value": data["src_inst_id"]},
                    {"field": "model_asst_id", "type": "str=", "value": data["model_asst_id"]},
                ]
                src_edge = ag.query_edge(INSTANCE_ASSOCIATION, src_query_data)
                if src_edge:
                    raise BaseAppException("source instance already exists association!")

        # 1:1关联校验
        elif asso_info["mapping"] == "1:1":
            # 检查源和目标实例是否已经存在关联
            with GraphClient() as ag:
                # 作为源模型实例
                src_query_data = [
                    {"field": "src_inst_id", "type": "int=", "value": data["src_inst_id"]},
                    {"field": "model_asst_id", "type": "str=", "value": data["model_asst_id"]},
                ]
                src_edge = ag.query_edge(INSTANCE_ASSOCIATION, src_query_data)
                if src_edge:
                    raise BaseAppException("source instance already exists association!")

                # 作为目标模型实例
                dst_query_data = [
                    {"field": "dst_inst_id", "type": "int=", "value": data["dst_inst_id"]},
                    {"field": "model_asst_id", "type": "str=", "value": data["model_asst_id"]},
                ]
                dst_edge = ag.query_edge(INSTANCE_ASSOCIATION, dst_query_data)
                if dst_edge:
                    raise BaseAppException("destination instance already exists association!")
        else:
            raise BaseAppException("association mapping error! mapping={}".format(asso_info["mapping"]))

    @staticmethod
    def instance_association_create(data: dict, operator: str):
        """创建实例关联"""

        # 校验关联约束
        InstanceManage.check_asso_mapping(data)

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
                    raise BaseAppException("instance association repetition")

        asso_info = InstanceManage.instance_association_by_asso_id(edge["_id"])
        message = f"创建模型关联关系. 原模型: {asso_info['src']['model_id']} 原模型实例: {asso_info['src']['inst_name']}  目标模型ID: {asso_info['dst']['model_id']} 目标模型实例: {asso_info['dst'].get('inst_name') or asso_info['dst'].get('ip_addr', '')}"
        create_change_record_by_asso(INSTANCE_ASSOCIATION, CREATE_INST_ASST, asso_info, message=message,
                                     operator=operator)

        return edge

    @staticmethod
    def instance_association_delete(asso_id: int, operator: str):
        """删除实例关联"""

        asso_info = InstanceManage.instance_association_by_asso_id(asso_id)

        with GraphClient() as ag:
            ag.delete_edge(asso_id)

        message = f"删除模型关联关系. 原模型: {asso_info['src']['model_id']} 原模型实例: {asso_info['src'].get('inst_name') or asso_info['src'].get('ip_addr', '')}  目标模型ID: {asso_info['dst']['model_id']} 目标模型实例: {asso_info['dst'].get('inst_name') or asso_info['dst'].get('ip_addr', '')}"
        create_change_record_by_asso(INSTANCE_ASSOCIATION, DELETE_INST_ASST, asso_info, message=message,
                                     operator=operator)

    @staticmethod
    def instance_association_by_asso_id(asso_id: int):
        """根据关联ID查询实例关联"""
        with GraphClient() as ag:
            edge = ag.query_edge_by_id(asso_id, return_entity=True)
        return edge

    @staticmethod
    def query_entity_by_id(inst_id: int):
        """根据实例ID查询实例详情"""
        with GraphClient() as ag:
            entity = ag.query_entity_by_id(inst_id)
        return entity

    @staticmethod
    def query_entity_by_ids(inst_ids: list):
        """根据实例ID查询实例详情"""
        with GraphClient() as ag:
            entity_list = ag.query_entity_by_ids(inst_ids)
        return entity_list

    @staticmethod
    def download_import_template(model_id: str):
        """下载导入模板"""
        attrs = ModelManage.search_model_attr_v2(model_id)
        association = ModelManage.model_association_search(model_id)
        return Export(attrs, model_id=model_id, association=association).export_template()

    @staticmethod
    def inst_import(model_id: str, file_stream: bytes, operator: str):
        """实例导入"""
        attrs = ModelManage.search_model_attr_v2(model_id)
        model_info = ModelManage.search_model_info(model_id)

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
        results = Import(model_id, attrs, exist_items, operator).import_inst_list(file_stream)

        change_records = [
            dict(
                inst_id=i["data"]["_id"],
                model_id=i["data"]["model_id"],
                before_data=i["data"],
                model_object=OPERATOR_INSTANCE,
                message=f"导入模型实例. 模型:{model_info['model_name']} 实例:{i['data'].get('inst_name') or i['data'].get('ip_addr', '')}",
            )
            for i in results
            if i["success"]
        ]
        batch_create_change_record(INSTANCE, CREATE_INST, change_records, operator=operator)

        return results

    def inst_import_support_edit(self, model_id: str, file_stream: bytes, operator: str):
        """实例导入-支持编辑"""
        attrs = ModelManage.search_model_attr_v2(model_id)
        model_info = ModelManage.search_model_info(model_id)

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])

        _import = Import(model_id, attrs, exist_items, operator)
        add_results, update_results, asso_result = _import.import_inst_list_support_edit(file_stream)

        # 检查是否存在验证错误
        if _import.validation_errors:
            error_summary = f"数据导入失败：发现 {len(_import.validation_errors)} 个数据验证错误\n"
            error_details = "\n".join(_import.validation_errors)
            logger.warning(f"模型 {model_id} 数据导入验证失败，错误数量: {len(_import.validation_errors)}")
            return {"success": False, "message": error_summary + error_details}

        add_changes = [
            dict(
                inst_id=i["data"]["_id"],
                model_id=i["data"]["model_id"],
                before_data=i["data"],
                model_object=OPERATOR_INSTANCE,
                message=f"导入模型实例. 模型:{model_info['model_name']} 新增模型实例:{i['data'].get('inst_name') or i['data'].get('ip_addr', '')}",
            )
            for i in add_results
            if i["success"]
        ]
        exist_items__id_map = {i["_id"]: i for i in exist_items}
        update_changes = [
            dict(
                inst_id=i["data"]["_id"],
                model_id=i["data"]["model_id"],
                before_data=exist_items__id_map[i["data"]["_id"]],
                model_object=OPERATOR_INSTANCE,
                message=f"导入模型实例. 模型:{model_info['model_name']} 更新模型实例:{i['data'].get('inst_name') or i['data'].get('ip_addr', '')}",
            )
            for i in update_results if i["success"]
        ]
        batch_create_change_record(INSTANCE, CREATE_INST, add_changes, operator=operator)
        batch_create_change_record(INSTANCE, UPDATE_INST, update_changes, operator=operator)
        result_message = self.format_result_message(_import.import_result_message)
        logger.info(f"模型 {model_id} 数据导入成功")
        return {"success": True, "message": result_message}

    @staticmethod
    def format_result_message(result: dict):
        key_map = {"add": "新增", "update": "更新", "asso": "关联"}
        add_mgs = ""
        for _key in ["add", "update", "asso"]:
            success_count = result[_key]["success"]
            fail_count = result[_key]["error"]
            data = result[_key]["data"]
            message = " ,".join(data)
            add_mgs += f"{key_map[_key]}: 成功{success_count}个，失败{fail_count}个. {message}\n"
        return add_mgs

    @staticmethod
    def inst_export(model_id: str, ids: list, user_groups: list, inst_names: list, created: str = "",
                    attr_list: list = [], association_list: list = []):
        """实例导出"""
        attrs = ModelManage.search_model_attr_v2(model_id)
        association = ModelManage.model_association_search(model_id)

        # 添加调试日志
        logger.info(f"导出参数 - model_id: {model_id}, ids: {ids}, association_list: {association_list}")
        logger.info(f"查询到的所有关联关系: {len(association)} 个")

        with GraphClient() as ag:
            # 使用新的基础权限过滤方法获取有权限的实例
            inst_list = ag.export_entities_with_permission(
                label=INSTANCE,
                teams=user_groups,
                inst_names=inst_names,
                creator=created,
                model_id=model_id,
                inst_ids=ids  # 在权限范围内过滤指定的实例ID
            )

        attrs = [i for i in attrs if i["attr_id"] in attr_list] if attr_list else attrs
        # 只有当用户明确选择了关联关系时才包含关联关系
        association = [i for i in association if
                       i["model_asst_id"] in association_list] if association_list else []
        
        logger.info(f"过滤后的关联关系: {len(association)} 个")
        
        return Export(attrs, model_id=model_id, association=association).export_inst_list(inst_list)

    @staticmethod
    def topo_search(inst_id: int):
        """拓扑查询"""
        with GraphClient() as ag:
            result = ag.query_topo(INSTANCE, inst_id)
        return result

    @staticmethod
    def topo_search_test_config(inst_id: int, model_id: str):
        """拓扑查询"""
        with GraphClient() as ag:
            result = ag.query_topo_test_config(INSTANCE, inst_id, model_id)
        return result

    @staticmethod
    def create_or_update(data: dict):
        if not data["show_fields"]:
            raise BaseAppException("展示字段不能为空！")
        ShowField.objects.update_or_create(
            defaults=data,
            model_id=data["model_id"],
            created_by=data["created_by"],
        )
        return data

    @staticmethod
    def get_info(model_id: str, created_by: str):
        obj = ShowField.objects.filter(created_by=created_by, model_id=model_id).first()
        result = dict(model_id=obj.model_id, show_fields=obj.show_fields) if obj else None
        return result

    @staticmethod
    def format_instance_permission_data(rules):
        # 构建实例权限过滤参数
        result = []
        if not rules:
            return result

        for group_id, models in rules.items():
            for model_id, permissions in models.items():
                # 检查是否有具体的实例权限限制
                has_specific_instances = False
                specific_instance_names = []

                for perm in permissions:
                    # id为'0'或'-1'表示全选，不需要过滤
                    if perm.get('id') not in ['0', '-1']:
                        has_specific_instances = True
                        # 这里的id实际上是inst_name
                        specific_instance_names.append(perm.get('id'))

                # 如果有具体的实例权限限制，添加到过滤参数中
                if has_specific_instances and specific_instance_names:
                    result.append({
                        'model_id': model_id,
                        'inst_names': specific_instance_names
                    })
        return result

    @staticmethod
    def add_inst_name_permission(inst_names):
        if not inst_names:
            return ""
        return f"n.inst_name IN {inst_names}"

    @classmethod
    def model_inst_count(cls, user_groups: list, inst_names: list, roles: list = [], created: str = ""):
        permission_params = InstanceManage.get_permission_params(user_groups=user_groups, roles=roles)
        inst_name_params = cls.add_inst_name_permission(inst_names)
        with GraphClient() as ag:
            data = ag.entity_count(
                label=INSTANCE,
                group_by_attr="model_id",
                params=[],
                permission_params=permission_params,
                inst_name_params=inst_name_params,
                created=created
            )
        return data

    @classmethod
    def fulltext_search(cls, user_groups: list, roles: list, search: str, inst_names: list, created: str = ""):
        """全文检索"""
        permission_params = InstanceManage.get_permission_params(user_groups, roles)
        inst_name_params = cls.add_inst_name_permission(inst_names)

        with GraphClient() as ag:
            data = ag.full_text(search=search, permission_params=permission_params,
                                inst_name_params=inst_name_params, created=created)
        return data
