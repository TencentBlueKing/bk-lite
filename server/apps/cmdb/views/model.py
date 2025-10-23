import copy

from rest_framework import viewsets, status
from rest_framework.decorators import action

from apps.cmdb.constants import ASSOCIATION_TYPE, OPERATOR_MODEL, PERMISSION_MODEL, OPERATE, VIEW, APP_NAME
from apps.cmdb.language.service import SettingLanguage
from apps.cmdb.models import DELETE_INST, UPDATE_INST
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.base import get_default_group_id, format_groups_params
from apps.cmdb.utils.change_record import create_change_record
from apps.cmdb.utils.permisssion_util import CmdbRulesFormatUtil
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.permission_utils import get_permission_rules, get_permissions_rules
from apps.core.utils.web_utils import WebUtils


class ModelViewSet(viewsets.ViewSet):

    @property
    def default_group_id(self):
        return get_default_group_id()[0]

    @staticmethod
    def model_add_permission(model_list, team_id: int, permission_instances_map: dict, teams: set):
        # 默认group为default的判断 全部人都可以查看
        for model_info in model_list:
            model_id = model_info["model_id"]
            if model_id in permission_instances_map:
                model_info['permission'] = permission_instances_map[model_id]
            else:
                group = model_info["group"]
                if team_id in group:
                    model_info['permission'] = [VIEW, OPERATE]
                elif set(group) & teams:
                    model_info['permission'] = [VIEW, OPERATE]
                else:
                    model_info['permission'] = [VIEW]

        return permission_instances_map

    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="get_model_info/(?P<model_id>.+?)")
    def get_model_info(self, request, model_id: str):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_MODEL}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        team = _permission_rules.get("team", [])
        _team = format_groups_params(teams=team)
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=VIEW,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=model_info,
                                                                   default_group_id=self.default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        self.model_add_permission(permission_instances_map=permission_instances_map,
                                  model_list=[model_info], team_id=int(current_team), teams=set(team))

        return WebUtils.response_success(model_info)

    @HasPermission("model_management-Add Model")
    def create(self, request):
        result = ModelManage.create_model(request.data, username=request.user.username)
        return WebUtils.response_success(result)

    @HasPermission("model_management-View")
    def list(self, request):
        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permissions_rules(user=request.user,
                                                  current_team=current_team, app_name=APP_NAME,
                                                  permission_key=PERMISSION_MODEL
                                                  )
        rules = _permission_rules.get("instance", [])
        group_list = _permission_rules.get("team", [])
        team = copy.deepcopy(group_list)
        group_list.append(self.default_group_id)
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        model_id_list = list(permission_instances_map.keys())
        result = ModelManage.search_model(language=request.user.locale, model_list=model_id_list,
                                          group_list=list(set(group_list)))

        # 补充权限
        self.model_add_permission(permission_instances_map=permission_instances_map,
                                  model_list=result, team_id=int(current_team), teams=set(team))

        return WebUtils.response_success(result)

    @HasPermission("model_management-Delete Model")
    def destroy(self, request, pk: str):
        model_id = pk
        model_info = ModelManage.search_model_info(pk)
        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_MODEL}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)

        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=OPERATE,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=model_info,
                                                                   default_group_id=self.default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN)

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

    @HasPermission("model_management-Edit Model")
    def update(self, request, pk: str):
        model_id = pk
        model_info = ModelManage.search_model_info(pk)
        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_MODEL}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=OPERATE,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=model_info,
                                                                   default_group_id=self.default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        data = ModelManage.update_model(model_info.get("_id"), request.data)
        create_change_record(operator=request.user.username, model_id=model_info["model_id"], label="模型管理",
                             _type=UPDATE_INST, message=f"修改模型. 模型名称: {model_info['model_name']}",
                             inst_id=model_info['_id'], model_object=OPERATOR_MODEL)
        return WebUtils.response_success(data)

    @HasPermission("model_management-Add Model")
    @action(detail=False, methods=["post"], url_path="association")
    def model_association_create(self, request):
        current_team = int(request.COOKIES.get("current_team"))
        src_model_id = request.data["src_model_id"]
        dst_model_id = request.data["dst_model_id"]

        # 检查源模型权限
        src_model_info = ModelManage.search_model_info(src_model_id)
        if not src_model_info:
            return WebUtils.response_error("源模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        _src_permission_rules = get_permission_rules(user=request.user,
                                                     current_team=current_team, app_name=APP_NAME,
                                                     permission_key=f"{PERMISSION_MODEL}.{src_model_id}"
                                                     )
        src_rules = _src_permission_rules.get("instance", [])
        src_permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=src_rules)
        src_has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                       operator=OPERATE,
                                                                       model_id=src_model_id,
                                                                       permission_instances_map=src_permission_instances_map,
                                                                       team_id=current_team,
                                                                       instance=src_model_info,
                                                                       default_group_id=self.default_group_id)
        if not src_has_permission:
            return WebUtils.response_error("抱歉！您没有源模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        # 检查目标模型权限
        dst_model_info = ModelManage.search_model_info(dst_model_id)
        if not dst_model_info:
            return WebUtils.response_error("目标模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        _dst_permission_rules = get_permission_rules(user=request.user,
                                                     current_team=current_team, app_name=APP_NAME,
                                                     permission_key=f"{PERMISSION_MODEL}.{dst_model_id}"
                                                     )
        dst_rules = _dst_permission_rules.get("instance", [])
        dst_permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=dst_rules)

        dst_has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                       operator=OPERATE,
                                                                       model_id=dst_model_id,
                                                                       permission_instances_map=dst_permission_instances_map,
                                                                       team_id=current_team,
                                                                       instance=dst_model_info,
                                                                       default_group_id=self.default_group_id)
        if not dst_has_permission:
            return WebUtils.response_error("抱歉！您没有目标模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        model_asst_id = f'{src_model_id}_{request.data["asst_id"]}_{dst_model_id}'
        result = ModelManage.model_association_create(
            src_id=src_model_info["_id"], dst_id=dst_model_info["_id"], model_asst_id=model_asst_id, **request.data
        )
        return WebUtils.response_success(result)

    @HasPermission("model_management-Delete Model")
    @action(detail=False, methods=["delete"], url_path="association/(?P<model_asst_id>.+?)")
    def model_association_delete(self, request, model_asst_id: str):
        current_team = int(request.COOKIES.get("current_team"))
        association_info = ModelManage.model_association_info_search(model_asst_id)
        src_model_id = association_info['src_model_id']
        dst_model_id = association_info['dst_model_id']

        # 检查源模型权限
        src_model_info = ModelManage.search_model_info(src_model_id)
        if not src_model_info:
            return WebUtils.response_error("源模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        _src_permission_rules = get_permission_rules(user=request.user,
                                                     current_team=current_team, app_name=APP_NAME,
                                                     permission_key=f"{PERMISSION_MODEL}.{src_model_id}"
                                                     )
        src_rules = _src_permission_rules.get("instance", [])
        src_permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=src_rules)
        src_has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                       operator=OPERATE,
                                                                       model_id=src_model_id,
                                                                       permission_instances_map=src_permission_instances_map,
                                                                       team_id=current_team,
                                                                       instance=src_model_info,
                                                                       default_group_id=self.default_group_id)
        if not src_has_permission:
            return WebUtils.response_error("抱歉！您没有源模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        # 检查目标模型权限
        dst_model_info = ModelManage.search_model_info(dst_model_id)
        if not dst_model_info:
            return WebUtils.response_error("目标模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        _dst_permission_rules = get_permission_rules(user=request.user,
                                                     current_team=current_team, app_name=APP_NAME,
                                                     permission_key=f"{PERMISSION_MODEL}.{dst_model_id}"
                                                     )
        dst_rules = _dst_permission_rules.get("instance", [])
        dst_permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=dst_rules)

        dst_has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                       operator=OPERATE,
                                                                       model_id=dst_model_id,
                                                                       permission_instances_map=dst_permission_instances_map,
                                                                       team_id=current_team,
                                                                       instance=dst_model_info,
                                                                       default_group_id=self.default_group_id
                                                                       )
        if not dst_has_permission:
            return WebUtils.response_error("抱歉！您没有目标模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        ModelManage.model_association_delete(association_info.get("_id"))
        return WebUtils.response_success()

    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="(?P<model_id>.+?)/association")
    def model_association_list(self, request, model_id: str):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_MODEL}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=VIEW,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=model_info,
                                                                   default_group_id=self.default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        result = ModelManage.model_association_search(model_id)
        return WebUtils.response_success(result)

    @HasPermission("model_management-Add Model")
    @action(detail=False, methods=["post"], url_path="(?P<model_id>.+?)/attr")
    def model_attr_create(self, request, model_id):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_MODEL}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=OPERATE,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=model_info,
                                                                   default_group_id=self.default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        result = ModelManage.create_model_attr(model_id, request.data, username=request.user.username)
        return WebUtils.response_success(result)

    @HasPermission("model_management-Edit Model")
    @action(detail=False, methods=["put"], url_path="(?P<model_id>.+?)/attr_update")
    def model_attr_update(self, request, model_id):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_MODEL}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=OPERATE,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=model_info,
                                                                   default_group_id=self.default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        result = ModelManage.update_model_attr(model_id, request.data, username=request.user.username)
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
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_MODEL}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=OPERATE,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=model_info,
                                                                   default_group_id=self.default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        result = ModelManage.delete_model_attr(model_id, attr_id, username=request.user.username)
        return WebUtils.response_success(result)

    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="(?P<model_id>.+?)/attr_list")
    def model_attr_list(self, request, model_id: str):
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        current_team = int(request.COOKIES.get("current_team"))
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_MODEL}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)

        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_MODEL,
                                                                   operator=VIEW,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=model_info,
                                                                   default_group_id=self.default_group_id)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此模型的权限", status_code=status.HTTP_403_FORBIDDEN)

        result = ModelManage.search_model_attr(model_id, request.user.locale)
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
                    "asst_name": lan.get_val("ASSOCIATION_TYPE", asso["asst_id"]) or asso["asst_name"],
                    "is_pre": asso["is_pre"],
                }
            )

        return WebUtils.response_success(result)
