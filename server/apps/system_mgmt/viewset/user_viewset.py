from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.logger import logger
from apps.system_mgmt.services.user_manage import UserManage


class UserViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["GET"])
    def search_user_list(self, request):
        _first, _max = UserManage.get_first_and_max(request.query_params)
        kwargs = {
            "first": _first,
            "max": _max,
            "search": request.GET.get("search", ""),
        }
        data = UserManage().user_list(kwargs, request.query_params.get("group_id", ""))
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["GET"])
    def user_all(self, request):
        data = UserManage().user_all()
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    def get_user_detail(self, request):
        pk = request.data.get("user_id")
        client_id = request.data.get("id")
        data = UserManage().get_user_info(pk, client_id)
        return JsonResponse({"result": True, "data": data})

    # @action(detail=False, methods=["GET"])
    # def get_users_in_role(self, request, role_name: str):
    #     data = UserManage().user_list_by_role(role_name)
    #     return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    def create_user(self, request):
        try:
            data = UserManage().user_create(request.data)
            return JsonResponse({"result": True, "data": data})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": str(e)})

    @action(detail=False, methods=["POST"])
    def reset_password(self, request):
        try:
            UserManage().reset_pwd(request.data)
            return JsonResponse({"result": True})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": str(e)})

    @action(detail=False, methods=["POST"])
    def delete_user(self, request):
        user_ids = request.data.get("user_ids")
        UserManage().user_delete(user_ids)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    def update_user(self, request):
        params = request.data
        pk = params.pop("user_id")
        UserManage().user_update(params, pk)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    def reset_user_password(self, request):
        pk = request.data.get("user_id")
        data = UserManage().user_reset_password(request.data, pk)
        return JsonResponse({"result": True, "data": data})

    @action(detail=True, methods=["POST"])
    def assign_user_groups(self, request):
        pk = request.data.get("user_id")
        UserManage().user_add_groups(request.data, pk)
        return JsonResponse({"result": True})

    @action(detail=True, methods=["POST"])
    def unassign_user_groups(self, request):
        pk = request.data.get("user_id")
        UserManage().user_remove_groups(request.data, pk)
        return JsonResponse({"result": True})

    @action(detail=True, methods=["POST"])
    def my_userinfo_update(self, request):
        pk = request.data.get("user_id")
        data = UserManage().user_update(request.data, pk)
        return JsonResponse({"result": True, "data": data})

    @action(detail=True, methods=["POST"])
    def my_pwd_reset(self, request):
        pk = request.data.get("user_id")
        data = UserManage().user_reset_password(request.data, pk)
        return JsonResponse({"result": True, "data": data})
