# -- coding: utf-8 --
# @File: field_group.py
# @Time: 2026/1/4
# @Author: windyzhao

from rest_framework import viewsets, status
from rest_framework.decorators import action

from apps.cmdb.constants.constants import PERMISSION_MODEL, VIEW
from apps.cmdb.filters.field_group import FieldGroupFilter
from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.serializers.field_group import (
    FieldGroupSerializer,
    FieldGroupCreateSerializer,
    FieldGroupUpdateSerializer,
    FieldGroupMoveSerializer,
    BatchUpdateAttrGroupSerializer,
)
from apps.cmdb.services.field_group import FieldGroupService
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.base import get_default_group_id
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination


class FieldGroupViewSet(viewsets.ModelViewSet):
    """字段分组管理视图集"""

    queryset = FieldGroup.objects.all().order_by("model_id", "order")
    serializer_class = FieldGroupSerializer
    filterset_class = FieldGroupFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("model_management-View")
    def list(self, request, *args, **kwargs):
        """
        获取分组列表

        Query参数:
        - model_id: 模型ID（必填，通过查询参数传递）
        - group_name: 分组名称（可选，模糊搜索）
        """
        return super().list(request, *args, **kwargs)

    @HasPermission("model_management-View")
    def retrieve(self, request, *args, **kwargs):
        """获取分组详情"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return WebUtils.response_success(serializer.data)

    @HasPermission("model_management-Edit Model")
    def create(self, request, *args, **kwargs):
        """
        创建分组

        请求体:
        {
            "model_id": "host",        // 必填
            "group_name": "基本信息",  // 必填
            "description": "描述信息",  // 可选
            "is_collapsed": false      // 可选
        }
        """
        model_id = request.data.get("model_id")
        if not model_id:
            return WebUtils.response_error("model_id不能为空")

        serializer = FieldGroupCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return WebUtils.response_error(
                serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            group = FieldGroupService.create_group(
                model_id=model_id,
                group_name=serializer.validated_data["group_name"],
                created_by=request.user.username,
                description=serializer.validated_data.get("description", ""),
                is_collapsed=serializer.validated_data.get("is_collapsed", False),
            )

            result_serializer = FieldGroupSerializer(group)
            return WebUtils.response_success(result_serializer.data)

        except BaseAppException as e:
            return WebUtils.response_error(str(e))

    @HasPermission("model_management-Edit Model")
    def update(self, request, *args, **kwargs):
        """
        修改分组

        请求体:
        {
            "group_name": "新名称",    // 必填
            "description": "描述",     // 可选
            "is_collapsed": true       // 可选
        }
        """
        instance = self.get_object()

        serializer = FieldGroupUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return WebUtils.response_error(
                serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            group = FieldGroupService.update_group(
                group=instance,
                new_group_name=serializer.validated_data.get("group_name"),
                description=serializer.validated_data.get("description"),
                is_collapsed=serializer.validated_data.get("is_collapsed"),
            )

            result_serializer = FieldGroupSerializer(group)
            return WebUtils.response_success(result_serializer.data)

        except BaseAppException as e:
            return WebUtils.response_error(str(e))

    @HasPermission("model_management-Delete Model")
    def destroy(self, request, *args, **kwargs):
        """
        删除分组

        返回:
        {
            "success": true,
            "message": "删除成功"
        }
        """
        instance = self.get_object()

        try:
            result = FieldGroupService.delete_group(group=instance)
            return WebUtils.response_success(result)

        except BaseAppException as e:
            return WebUtils.response_error(str(e))

    @HasPermission("model_management-Edit Model")
    @action(detail=True, methods=["post"], url_path="move")
    def move(self, request, *args, **kwargs):
        """
        移动分组顺序

        请求体:
        {
            "direction": "up"  // "up" 或 "down"
        }

        返回:
        {
            "success": true,
            "message": "修改成功",
            "new_orders": [
                {"group_name": "基本信息", "order": 1},
                {"group_name": "网络信息", "order": 2}
            ]
        }
        """
        instance = self.get_object()

        serializer = FieldGroupMoveSerializer(data=request.data)
        if not serializer.is_valid():
            return WebUtils.response_error(
                serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = FieldGroupService.move_group(
                model_id=instance.model_id,
                group_name=instance.group_name,
                direction=serializer.validated_data["direction"],
            )
            return WebUtils.response_success(result)

        except BaseAppException as e:
            return WebUtils.response_error(str(e))

    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="full_info")
    def full_info(self, request, *args, **kwargs):
        """
        获取模型完整信息（含分组和属性）

        Query参数:
        - model_id: 模型ID（必填）

        返回:
        {
            "model_id": "host",
            "model_name": "主机",
            "groups": [
                {
                    "group_name": "基本信息",
                    "order": 1,
                    "attrs": [...],
                    "attrs_count": 5,
                    "can_move_up": false,
                    "can_move_down": true,
                    "can_delete": true
                }
            ],
            "total_groups": 3,
            "total_attrs": 15
        }
        """

        model_id = request.query_params.get("model_id")
        if not model_id:
            return WebUtils.response_error("model_id不能为空")

        model_info = ModelManage.search_model_info(model_id)

        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request,
                                                                             model_id=model_info["model_id"],
                                                                             permission_type=PERMISSION_MODEL)

        user_groups = {i["id"] for i in request.user.group_list}
        organizations = list(set(model_info["group"]) & user_groups)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error("抱歉！您没有此模型的查询权限", status_code=status.HTTP_403_FORBIDDEN)

        default_group_id = get_default_group_id()[0]
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=VIEW,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permissions_map,
                                                                   instance=model_info,
                                                                   default_group_id=default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的查询权限", status_code=status.HTTP_403_FORBIDDEN)

        try:
            data = FieldGroupService.get_model_with_groups(
                model_id=model_id, language=request.user.locale
            )
            return WebUtils.response_success(data)

        except BaseAppException as e:
            return WebUtils.response_error(str(e))

    @HasPermission("model_management-Edit Model")
    @action(detail=False, methods=["put"], url_path="batch_update_attrs")
    def batch_update_attrs(self, request, *args, **kwargs):
        """
        批量更新字段分组

        请求体:
        {
            "model_id": "host",  // 必填
            "updates": [
                {"attr_id": "ip_addr", "group_name": "网络信息"},
                {"attr_id": "port", "group_name": "网络信息"},
                {"attr_id": "cpu_model", "group_name": "硬件信息"}
            ]
        }

        返回:
        {
            "success": true,
            "message": "成功更新3个字段的分组",
            "updated_count": 3
        }
        """
        model_id = request.data.get("model_id")
        if not model_id:
            return WebUtils.response_error("model_id不能为空")

        serializer = BatchUpdateAttrGroupSerializer(data=request.data)
        if not serializer.is_valid():
            return WebUtils.response_error(
                serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = FieldGroupService.batch_update_attrs_group(
                model_id=model_id, updates=serializer.validated_data["updates"]
            )
            return WebUtils.response_success(result)

        except BaseAppException as e:
            return WebUtils.response_error(str(e))

    @HasPermission("model_management-Edit Model")
    @action(detail=False, methods=["post"], url_path="update_attr_group")
    def update_attr_group(self, request, *args, **kwargs):
        """
        修改单个属性的分组（支持跨分组移动）

        请求体:
        {
            "model_id": "host",           // 必填
            "attr_id": "inst_name",       // 必填
            "group_name": "基本信息"      // 必填
            "order_id": 2               // 可选，属性在新分组中的顺序位置
        }

        返回:
        {
            "success": true,
            "message": "成功将属性'inst_name'从'网络信息'移动到'基本信息'",
            "attr_id": "inst_name",
            "old_group": "网络信息",
            "new_group": "基本信息"
        }
        """
        model_id = request.data.get("model_id")
        attr_id = request.data.get("attr_id")
        group_name = request.data.get("group_name")
        order_id = request.data.get("order_id")

        if not model_id:
            return WebUtils.response_error("model_id不能为空")
        if not attr_id:
            return WebUtils.response_error("attr_id不能为空")
        if not group_name:
            return WebUtils.response_error("group_name不能为空")

        try:
            result = FieldGroupService.update_attr_group(
                model_id=model_id, attr_id=attr_id, new_group_name=group_name, order_id=order_id
            )
            return WebUtils.response_success(result)

        except BaseAppException as e:
            return WebUtils.response_error(str(e))

    @HasPermission("model_management-Edit Model")
    @action(detail=False, methods=["post"], url_path="reorder_group_attrs")
    def reorder_group_attrs(self, request, *args, **kwargs):
        """
        调整分组内属性的顺序

        请求体:
        {
            "model_id": "host",              // 必填
            "group_name": "基本信息",        // 必填
            "attr_orders": ["c", "a", "b"]   // 必填，属性ID数组（新顺序）
        }

        返回:
        {
            "success": true,
            "message": "成功调整分组'基本信息'的属性顺序",
            "group_name": "基本信息",
            "attr_orders": ["c", "a", "b"]
        }
        """
        model_id = request.data.get("model_id")
        group_name = request.data.get("group_name")
        attr_orders = request.data.get("attr_orders")

        if not model_id:
            return WebUtils.response_error("model_id不能为空")
        if not group_name:
            return WebUtils.response_error("group_name不能为空")
        if not attr_orders or not isinstance(attr_orders, list):
            return WebUtils.response_error("attr_orders必须是属性ID数组")

        try:
            result = FieldGroupService.reorder_group_attrs(
                model_id=model_id, group_name=group_name, attr_orders=attr_orders
            )
            return WebUtils.response_success(result)

        except BaseAppException as e:
            return WebUtils.response_error(str(e))
