from rest_framework import viewsets, status
from rest_framework.decorators import action

from apps.cmdb.constants.constants import (
    ASSOCIATION_TYPE,
    OPERATOR_MODEL,
    PERMISSION_MODEL,
    OPERATE,
    VIEW,
)
from apps.cmdb.validators import IdentifierValidator
from apps.cmdb.language.service import SettingLanguage
from apps.cmdb.models import DELETE_INST, UPDATE_INST, FieldGroup
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.base import get_default_group_id
from apps.cmdb.utils.change_record import create_change_record
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils


class ModelViewSet(CmdbPermissionMixin, viewsets.ViewSet):

    @property
    def default_group_id(self):
        return get_default_group_id()[0]

    @staticmethod
    def model_add_permission(
        model_list, permission_instances_map: dict, default_group=None
    ):
        # 默认group为default的判断 全部人都可以查看
        group_instances_map = CmdbRulesFormatUtil.format_organizations_instances_map(
            permission_instances_map
        )
        for model_info in model_list:
            model_info["permission"] = []

            groups = model_info["group"]
            # 多个实力权限都可以配置一样
            for group in groups:
                if group == default_group:
                    model_info["permission"].append(VIEW)

                if group not in group_instances_map:
                    continue
                for _permission in group_instances_map[group]["permission"]:
                    if _permission not in model_info["permission"]:
                        model_info["permission"].append(_permission)

            if not model_info["permission"]:
                if model_info["model_id"] in group_instances_map:
                    model_info["permission"] = list(
                        group_instances_map[model_info["model_id"]]["permission"]
                    )

        return permission_instances_map

    def organizations(self, request, instance):
        """Get user's organizations for model. Delegates to mixin."""
        return self.get_user_organizations(request, instance, "group")

    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="get_model_info/(?P<model_id>.+?)")
    def get_model_info(self, request, model_id: str):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error(
                "模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request,
            model_id=model_info["model_id"],
            permission_type=PERMISSION_MODEL,
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        self.model_add_permission(
            permission_instances_map=permissions_map,
            model_list=[model_info],
            default_group=self.default_group_id,
        )

        return WebUtils.response_success(model_info)

    @HasPermission("model_management-Add Model")
    def create(self, request):
        model_id = request.data.get("model_id", "")
        if not IdentifierValidator.is_valid(model_id):
            return WebUtils.response_error(
                IdentifierValidator.get_error_message("模型ID")
            )

        result = ModelManage.create_model(request.data, username=request.user.username)
        return WebUtils.response_success(result)

    @HasPermission("model_management-View")
    def list(self, request):
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request, model_id="", permission_type=PERMISSION_MODEL
        )
        current_team = int(request.COOKIES.get("current_team"))
        # 默认的组织模型 全部人都可以查看
        # TODO 默认组织的权限，默认组织应该全部都有VIEW权限，但是操作权限就需要看组织了，组织全选或者配置了组织权限的，就再补充操作权限
        default_group_id = self.default_group_id
        default_group_permission = {"permission_instances_map": {}, "inst_names": []}
        if default_group_id != current_team:
            default_group_permission["__default_model"] = [VIEW]

        default_group_id_permission = permissions_map.pop(
            default_group_id, default_group_permission
        )
        permissions_map[default_group_id] = default_group_id_permission
        result = ModelManage.search_model(
            language=request.user.locale, permissions_map=permissions_map
        )
        # 重新把配置了的默认组织权限加上，因为默认组织权限是全部人都有查看的权限的 但是操作权限需要单独配置
        permissions_map[default_group_id]["inst_names"] = default_group_id_permission[
            "inst_names"
        ]
        # 补充权限
        self.model_add_permission(
            permission_instances_map=permissions_map,
            model_list=result,
            default_group=default_group_id,
        )

        return WebUtils.response_success(result)

    @HasPermission("model_management-Delete Model")
    def destroy(self, request, pk: str):
        model_id = pk
        model_info = ModelManage.search_model_info(pk)
        if not model_info:
            return WebUtils.response_error(
                "模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request,
            model_id=model_info["model_id"],
            permission_type=PERMISSION_MODEL,
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=OPERATE,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        # 校验模型是否存在关联
        ModelManage.check_model_exist_association(pk)
        # 校验模型是否存在实例
        ModelManage.check_model_exist_inst(pk)
        # 执行删除
        model_info = ModelManage.search_model_info(pk)
        ModelManage.delete_model(model_info.get("_id"))

        create_change_record(
            operator=request.user.username,
            model_id=model_info["model_id"],
            label="模型管理",
            _type=DELETE_INST,
            message=f"删除模型. 模型名称: {model_info['model_name']}",
            inst_id=model_info["_id"],
            model_object=OPERATOR_MODEL,
        )

        # 删除该模型下的所有字段分组配置，避免属性变更后字段分组配置不一致的问题
        FieldGroup.objects.filter(model_id=model_info["model_id"]).delete()

        return WebUtils.response_success()

    @HasPermission("model_management-Edit Model")
    def update(self, request, pk: str):
        model_id = pk
        model_info = ModelManage.search_model_info(pk)
        if not model_info:
            return WebUtils.response_error(
                "模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request,
            model_id=model_info["model_id"],
            permission_type=PERMISSION_MODEL,
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=OPERATE,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        data = ModelManage.update_model(model_info.get("_id"), request.data)
        create_change_record(
            operator=request.user.username,
            model_id=model_info["model_id"],
            label="模型管理",
            _type=UPDATE_INST,
            message=f"修改模型. 模型名称: {model_info['model_name']}",
            inst_id=model_info["_id"],
            model_object=OPERATOR_MODEL,
        )
        return WebUtils.response_success(data)

    @HasPermission("model_management-Add Model")
    @action(detail=False, methods=["post"], url_path="association")
    def model_association_create(self, request):
        src_model_id = request.data["src_model_id"]
        dst_model_id = request.data["dst_model_id"]

        # 检查源模型权限
        src_model_info = ModelManage.search_model_info(src_model_id)
        if not src_model_info:
            return WebUtils.response_error(
                "源模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=src_model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, src_model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        src_has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=VIEW,
            model_id=src_model_id,
            permission_instances_map=permissions_map,
            instance=src_model_info,
            default_group_id=self.default_group_id,
        )
        if not src_has_permission:
            return WebUtils.response_error(
                "抱歉！您没有源模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        # 检查目标模型权限
        dst_model_info = ModelManage.search_model_info(dst_model_id)
        if not dst_model_info:
            return WebUtils.response_error(
                "目标模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=dst_model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, dst_model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        dst_has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=VIEW,
            model_id=dst_model_id,
            permission_instances_map=permissions_map,
            instance=dst_model_info,
            default_group_id=self.default_group_id,
        )
        if not dst_has_permission:
            return WebUtils.response_error(
                "抱歉！您没有目标模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        model_asst_id = f"{src_model_id}_{request.data['asst_id']}_{dst_model_id}"
        result = ModelManage.model_association_create(
            src_id=src_model_info["_id"],
            dst_id=dst_model_info["_id"],
            model_asst_id=model_asst_id,
            **request.data,
        )
        return WebUtils.response_success(result)

    @HasPermission("model_management-Delete Model")
    @action(
        detail=False, methods=["delete"], url_path="association/(?P<model_asst_id>.+?)"
    )
    def model_association_delete(self, request, model_asst_id: str):
        association_info = ModelManage.model_association_info_search(model_asst_id)
        src_model_id = association_info["src_model_id"]
        dst_model_id = association_info["dst_model_id"]

        # 检查源模型权限
        src_model_info = ModelManage.search_model_info(src_model_id)
        if not src_model_info:
            return WebUtils.response_error(
                "源模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        src_permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=src_model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, src_model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有源模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        src_has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=OPERATE,
            model_id=src_model_id,
            permission_instances_map=src_permissions_map,
            instance=src_model_info,
            default_group_id=self.default_group_id,
        )
        if not src_has_permission:
            return WebUtils.response_error(
                "抱歉！您没有源模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        # 检查目标模型权限
        dst_model_info = ModelManage.search_model_info(dst_model_id)
        if not dst_model_info:
            return WebUtils.response_error(
                "目标模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        dst_permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=dst_model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, dst_model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有目标模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        dst_has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=OPERATE,
            model_id=dst_model_id,
            permission_instances_map=dst_permissions_map,
            instance=dst_model_info,
            default_group_id=self.default_group_id,
        )
        if not dst_has_permission:
            return WebUtils.response_error(
                "抱歉！您没有目标模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        ModelManage.model_association_delete(association_info.get("_id"))
        return WebUtils.response_success()

    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="(?P<model_id>.+?)/association")
    def model_association_list(self, request, model_id: str):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error(
                "模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        result = ModelManage.model_association_search(model_id)
        return WebUtils.response_success(result)

    @HasPermission("model_management-Add Model")
    @action(detail=False, methods=["post"], url_path="(?P<model_id>.+?)/attr")
    def model_attr_create(self, request, model_id):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error(
                "模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=OPERATE,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        result = ModelManage.create_model_attr(
            model_id, request.data, username=request.user.username
        )
        # 把分组信息也更新了
        attr_group = request.data.get("attr_group")
        field_group = FieldGroup.objects.filter(
            model_id=model_id, group_name=attr_group
        ).first()
        if field_group:
            attr_id = request.data.get("attr_id")
            attr_orders = field_group.attr_orders
            if attr_id not in attr_orders:
                attr_orders.append(attr_id)
                field_group.attr_orders = attr_orders
                field_group.save()

        return WebUtils.response_success(result)

    @HasPermission("model_management-Edit Model")
    @action(detail=False, methods=["put"], url_path="(?P<model_id>.+?)/attr_update")
    def model_attr_update(self, request, model_id):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error(
                "模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=OPERATE,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        result = ModelManage.update_model_attr(
            model_id, request.data, username=request.user.username
        )

        # 把分组信息也更新了
        attr_group = request.data.get("attr_group")
        field_group = FieldGroup.objects.filter(
            model_id=model_id, group_name=attr_group
        ).first()
        if field_group:
            attr_id = request.data.get("attr_id")
            attr_orders = field_group.attr_orders
            if attr_id not in attr_orders:
                attr_orders.append(attr_id)
                field_group.attr_orders = attr_orders
                field_group.save()

        # 如果修改的是枚举类型字段，需要更新所有实例的 _display 冗余字段
        attr_type = request.data.get("attr_type")
        if attr_type == "enum":
            attr_id = request.data.get("attr_id")
            new_options = request.data.get("option", [])
            ModelManage.update_enum_instances_display(model_id, attr_id, new_options)

        return WebUtils.response_success(result)

    @HasPermission("model_management-Delete Model")
    @action(
        detail=False,
        methods=["delete"],
        url_path="(?P<model_id>.+?)/attr/(?P<attr_id>.+?)",
    )
    def model_attr_delete(self, request, model_id: str, attr_id: str):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error(
                "模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=OPERATE,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        result = ModelManage.delete_model_attr(
            model_id, attr_id, username=request.user.username
        )

        # 把分组信息也更新了
        field_group = FieldGroup.objects.filter(
            model_id=model_id, attr_orders__contains=attr_id
        ).first()
        if field_group:
            field_group.attr_orders = [
                i for i in field_group.attr_orders if i != attr_id
            ]
            field_group.save()

        return WebUtils.response_success(result)

    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="(?P<model_id>.+?)/attr_list")
    def model_attr_list(self, request, model_id: str):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error(
                "模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        result = ModelManage.search_model_attr(model_id, request.user.locale)
        filtered_attrs = [attr for attr in result if not attr.get("is_display_field")]
        return WebUtils.response_success(filtered_attrs)

    @HasPermission("model_management-Add Model")
    @action(detail=False, methods=["post"], url_path="(?P<model_id>.+?)/copy")
    def model_copy(self, request, model_id: str):
        """
        复制模型
        请求参数：
        - new_model_id: 新模型ID（必填）
        - new_model_name: 新模型名称（必填）
        - classification_id: 模型分类ID（可选，不传则继承源模型）
        - group: 组织列表（可选，不传则继承源模型）
        - icn: 图标（可选，不传则继承源模型）
        - copy_attributes: 是否复制属性（可选，默认False）
        - copy_relationships: 是否复制关系（可选，默认False）
        """
        # 检查源模型是否存在
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error(
                "源模型不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        # 检查源模型权限
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id, permission_type=PERMISSION_MODEL
        )

        organizations = self.organizations(request, model_info)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=self.default_group_id,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        # 获取请求参数
        new_model_id = request.data.get("new_model_id")
        new_model_name = request.data.get("new_model_name")
        classification_id = request.data.get(
            "classification_id"
        )  # 可选，不传则继承源模型
        group = request.data.get("group")  # 可选，不传则继承源模型
        icn = request.data.get("icn")  # 可选，不传则继承源模型
        copy_attributes = request.data.get("copy_attributes", False)
        copy_relationships = request.data.get("copy_relationships", False)

        # 参数校验
        if not new_model_id:
            return WebUtils.response_error(
                "新模型ID不能为空", status_code=status.HTTP_400_BAD_REQUEST
            )

        if not IdentifierValidator.is_valid(new_model_id):
            return WebUtils.response_error(
                IdentifierValidator.get_error_message("新模型ID"),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not new_model_name:
            return WebUtils.response_error(
                "新模型名称不能为空", status_code=status.HTTP_400_BAD_REQUEST
            )

        if not copy_attributes and not copy_relationships:
            return WebUtils.response_error(
                "至少选择一种复制方式（属性或关系）",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 执行复制
        result = ModelManage.copy_model(
            src_model_id=model_id,
            new_model_id=new_model_id,
            new_model_name=new_model_name,
            classification_id=classification_id,
            group=group,
            icn=icn,
            copy_attributes=copy_attributes,
            copy_relationships=copy_relationships,
            username=request.user.username,
        )

        return WebUtils.response_success(result)

    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="model_association_type")
    def model_association_type(self, request):
        lan = SettingLanguage(request.user.locale)
        result = []
        for asso in ASSOCIATION_TYPE:
            result.append(
                {
                    "asst_id": asso["asst_id"],
                    "asst_name": lan.get_val("ASSOCIATION_TYPE", asso["asst_id"])
                    or asso["asst_name"],
                    "is_pre": asso["is_pre"],
                }
            )

        return WebUtils.response_success(result)
