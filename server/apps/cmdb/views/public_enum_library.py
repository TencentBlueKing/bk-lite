# -- coding: utf-8 --
# @File: public_enum_library.py
# @Time: 2026/3/9
# @Author: windyzhao
from rest_framework import status
from rest_framework.decorators import action

from apps.cmdb.models.public_enum_library import PublicEnumLibrary
from apps.cmdb.services import public_enum_library as library_service
from apps.cmdb.utils.base import (
    get_current_team_from_request,
    get_organization_and_children_ids,
)
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.viewset_utils import AuthViewSet
from apps.core.utils.web_utils import WebUtils


class PublicEnumLibraryViewSet(AuthViewSet):
    queryset = PublicEnumLibrary.objects.all()
    ORGANIZATION_FIELD = "team"

    def _get_user_team(self, request) -> list:
        return [g["id"] for g in getattr(request.user, "group_list", []) or []]

    @HasPermission("model_management-View")
    def list(self, request):
        current_team = get_current_team_from_request(request, required=False)
        include_children = request.COOKIES.get("include_children") == "1"

        if current_team and include_children:
            team = get_organization_and_children_ids(
                tree_data=request.user.group_tree, target_id=current_team
            )
            if not team:
                team = [current_team]
        elif current_team:
            team = [current_team]
        else:
            team = self._get_user_team(request)

        libraries = library_service.list_libraries(team=team)
        return WebUtils.response_success(libraries)

    @HasPermission("model_management-Edit Model")
    def create(self, request):
        payload = request.data
        operator = request.user.username
        try:
            result = library_service.create_library(payload, operator)
            return WebUtils.response_success(result)
        except BaseAppException as e:
            return WebUtils.response_error(
                str(e), status_code=status.HTTP_400_BAD_REQUEST
            )

    @HasPermission("model_management-Edit Model")
    def update(self, request, pk: str):
        payload = request.data
        operator = request.user.username
        try:
            result = library_service.update_library(pk, payload, operator)
            return WebUtils.response_success(result)
        except BaseAppException as e:
            if "不存在" in e.message:
                return WebUtils.response_error(
                    e.message, status_code=status.HTTP_404_NOT_FOUND
                )
            return WebUtils.response_error(
                e.message, status_code=status.HTTP_400_BAD_REQUEST
            )

    @HasPermission("model_management-Delete Model")
    def destroy(self, request, pk: str):
        operator = request.user.username
        try:
            library_service.delete_library(pk, operator)
            return WebUtils.response_success({"message": "删除成功"})
        except BaseAppException as e:
            if "不存在" in e.message:
                return WebUtils.response_error(
                    e.message, status_code=status.HTTP_404_NOT_FOUND
                )
            if e.data and "references" in e.data:
                return WebUtils.response_error(
                    response_data="",
                    error_message=e.message,
                    status_code=status.HTTP_409_CONFLICT,
                )
            return WebUtils.response_error(
                e.message, status_code=status.HTTP_400_BAD_REQUEST
            )

    @HasPermission("model_management-View")
    @action(detail=True, methods=["get"], url_path="references")
    def references(self, request, pk: str):
        try:
            library_service.get_library_or_raise(pk)
            references = library_service.find_library_references(pk)
            return WebUtils.response_success(references)
        except BaseAppException as e:
            if "不存在" in e.message:
                return WebUtils.response_error(
                    e.message, status_code=status.HTTP_404_NOT_FOUND
                )
            return WebUtils.response_error(
                e.message, status_code=status.HTTP_400_BAD_REQUEST
            )
