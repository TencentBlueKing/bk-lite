from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.cmdb.constants import ASSOCIATION_TYPE, OPERATOR_MODEL
from apps.cmdb.language.service import SettingLanguage
from apps.cmdb.models import DELETE_INST, UPDATE_INST
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.change_record import create_change_record
from apps.core.decorators.api_perminssion import HasRole
from apps.core.utils.web_utils import WebUtils


class ModelViewSet(viewsets.ViewSet):
    @swagger_auto_schema(
        operation_id="model_create",
        operation_description="创建模型",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "classification_id": openapi.Schema(type=openapi.TYPE_STRING, description="模型分类ID"),
                "model_id": openapi.Schema(type=openapi.TYPE_STRING, description="模型ID"),
                "model_name": openapi.Schema(type=openapi.TYPE_STRING, description="模型名称"),
                "icn": openapi.Schema(type=openapi.TYPE_STRING, description="图标"),
            },
            required=["classification_id", "model_id", "model_name", "icn"],
        ),
    )
    @HasRole(["admin"])
    def create(self, request):
        result = ModelManage.create_model(request.data, username=request.user.username)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="model_list",
        operation_description="查询模型",
    )
    def list(self, request):
        result = ModelManage.search_model(request.user.locale)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="model_delete",
        operation_description="删除模型",
        manual_parameters=[openapi.Parameter("id", openapi.IN_PATH, description="模型ID", type=openapi.TYPE_STRING)],
    )
    @HasRole(["admin"])
    def destroy(self, request, pk: str):
        # 校验模型是否存在关联
        ModelManage.check_model_exist_association(pk)
        # 校验模型是否存在实例
        ModelManage.check_model_exist_inst(pk)
        # 执行删除
        model_info = ModelManage.search_model_info(pk)
        ModelManage.delete_model(model_info.get("_id"))

        create_change_record(operator=request.user.username, model_id=model_info["model_id"], label="模型管理",
                             _type=DELETE_INST, message=f"删除模型. 模型名称: {model_info['model_name']}",
                             inst_id=model_info['_id'], model_object=OPERATOR_MODEL)
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_id="model_update",
        operation_description="更改模型信息",
        manual_parameters=[openapi.Parameter("id", openapi.IN_PATH, description="模型ID", type=openapi.TYPE_STRING)],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "classification_id": openapi.Schema(type=openapi.TYPE_STRING, description="模型分类ID"),
                "model_name": openapi.Schema(type=openapi.TYPE_STRING, description="模型名称"),
                "icn": openapi.Schema(type=openapi.TYPE_STRING, description="图标"),
            },
        ),
    )
    @HasRole(["admin"])
    def update(self, request, pk: str):
        model_info = ModelManage.search_model_info(pk)
        data = ModelManage.update_model(model_info.get("_id"), request.data)

        create_change_record(operator=request.user.username, model_id=model_info["model_id"], label="模型管理",
                             _type=UPDATE_INST, message=f"修改模型. 模型名称: {model_info['model_name']}",
                             inst_id=model_info['_id'], model_object=OPERATOR_MODEL)
        return WebUtils.response_success(data)

    @swagger_auto_schema(
        operation_id="model_association_create",
        operation_description="创建模型关联",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "asst_id": openapi.Schema(type=openapi.TYPE_STRING, description="关联关系"),
                "src_model_id": openapi.Schema(type=openapi.TYPE_STRING, description="源模型ID"),
                "dst_model_id": openapi.Schema(type=openapi.TYPE_STRING, description="目标模型ID"),
                "mapping": openapi.Schema(type=openapi.TYPE_STRING, description="约束"),
            },
            required=[
                "asst_id",
                "src_model_id",
                "dst_model_id",
                "mapping",
            ],
        ),
    )
    @HasRole(["admin"])
    @action(detail=False, methods=["post"], url_path="association")
    def model_association_create(self, request):
        model_asst_id = f'{request.data["src_model_id"]}_{request.data["asst_id"]}_{request.data["dst_model_id"]}'
        src_model_info = ModelManage.search_model_info(request.data["src_model_id"])
        dst_model_info = ModelManage.search_model_info(request.data["dst_model_id"])
        result = ModelManage.model_association_create(
            src_id=src_model_info["_id"], dst_id=dst_model_info["_id"], model_asst_id=model_asst_id, **request.data
        )
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="model_association_delete",
        operation_description="删除模型关联",
        manual_parameters=[
            openapi.Parameter(
                "model_asst_id",
                openapi.IN_PATH,
                description="模型关联ID",
                type=openapi.TYPE_STRING,
            )
        ],
    )
    @HasRole(["admin"])
    @action(detail=False, methods=["delete"], url_path="association/(?P<model_asst_id>.+?)")
    def model_association_delete(self, request, model_asst_id: str):
        association_info = ModelManage.model_association_info_search(model_asst_id)
        ModelManage.model_association_delete(association_info.get("_id"))
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_id="model_association_list",
        operation_description="查询模型关联",
        manual_parameters=[
            openapi.Parameter(
                "model_id",
                openapi.IN_PATH,
                description="模型ID",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    @action(detail=False, methods=["get"], url_path="(?P<model_id>.+?)/association")
    def model_association_list(self, request, model_id: str):
        result = ModelManage.model_association_search(model_id)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="model_attr_create",
        operation_description="创建模型属性",
        manual_parameters=[
            openapi.Parameter(
                "model_id",
                openapi.IN_PATH,
                description="模型ID",
                type=openapi.TYPE_STRING,
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "attr_id": openapi.Schema(type=openapi.TYPE_STRING, description="属性ID"),
                "attr_name": openapi.Schema(type=openapi.TYPE_STRING, description="属性名称"),
                "attr_type": openapi.Schema(type=openapi.TYPE_STRING, description="属性类型"),
                "is_only": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="是否唯一"),
                "is_required": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="必填项"),
                "editable": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="可编辑"),
                "option": openapi.Schema(
                    type=openapi.TYPE_ARRAY, description="选项", items=openapi.Schema(type=openapi.TYPE_STRING)
                ),
                "attr_group": openapi.Schema(type=openapi.TYPE_STRING, description="属性分组"),
            },
        ),
    )
    @HasRole(["admin"])
    @action(detail=False, methods=["post"], url_path="(?P<model_id>.+?)/attr")
    def model_attr_create(self, request, model_id):
        result = ModelManage.create_model_attr(model_id, request.data, username=request.user.username)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="model_attr_update",
        operation_description="更新模型属性信息",
        manual_parameters=[
            openapi.Parameter(
                "model_id",
                openapi.IN_PATH,
                description="模型ID",
                type=openapi.TYPE_STRING,
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "attr_id": openapi.Schema(type=openapi.TYPE_STRING, description="属性ID"),
                "attr_name": openapi.Schema(type=openapi.TYPE_STRING, description="属性名称"),
                "attr_type": openapi.Schema(type=openapi.TYPE_STRING, description="属性类型"),
                "is_only": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="是否唯一"),
                "is_required": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="必填项"),
                "editable": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="可编辑"),
                "option": openapi.Schema(type=openapi.TYPE_STRING, description="选项"),
                "attr_group": openapi.Schema(type=openapi.TYPE_STRING, description="属性分组"),
            },
        ),
    )
    @HasRole(["admin"])
    @action(detail=False, methods=["put"], url_path="(?P<model_id>.+?)/attr_update")
    def model_attr_update(self, request, model_id):
        result = ModelManage.update_model_attr(model_id, request.data, username=request.user.username)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="model_attr_delete",
        operation_description="删除模型属性",
        manual_parameters=[
            openapi.Parameter(
                "model_id",
                openapi.IN_PATH,
                description="模型ID",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "attr_id",
                openapi.IN_PATH,
                description="模型属性ID",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    @HasRole(["admin"])
    @action(
        detail=False,
        methods=["delete"],
        url_path="(?P<model_id>.+?)/attr/(?P<attr_id>.+?)",
    )
    def model_attr_delete(self, request, model_id: str, attr_id: str):
        result = ModelManage.delete_model_attr(model_id, attr_id, username=request.user.username)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="model_attr_list",
        operation_description="查询模型属性",
        manual_parameters=[
            openapi.Parameter(
                "model_id",
                openapi.IN_PATH,
                description="模型ID",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    @action(detail=False, methods=["get"], url_path="(?P<model_id>.+?)/attr_list")
    def model_attr_list(self, request, model_id: str):
        result = ModelManage.search_model_attr(model_id, request.user.locale)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="model_association_type",
        operation_description="查询模型关联类型",
    )
    @action(detail=False, methods=["get"], url_path="model_association_type")
    def model_association_type(self, request):
        lan = SettingLanguage(request.user.locale)
        result = []
        for asso in ASSOCIATION_TYPE:
            result.append(
                {
                    "asst_id": asso["asst_id"],
                    "asst_name": lan.get_val("ASSOCIATION_TYPE", asso["asst_id"]) or asso["asst_name"],
                    "is_pre": asso["is_pre"],
                }
            )

        return WebUtils.response_success(result)
