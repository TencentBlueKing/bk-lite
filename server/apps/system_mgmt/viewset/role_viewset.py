from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.system_mgmt.services.role_manage import RoleManage
from apps.system_mgmt.services.user_manage import UserManage


class RoleViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["POST"])
    def search_role_list(self, request):
        client_id = request.data.get("client_id", [])
        if not isinstance(client_id, list):
            client_id = [client_id]
        data = RoleManage().get_role_list(client_id)
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    def get_role_tree(self, request):
        client_list = request.data.get("client_list", [])
        data = RoleManage().get_role_tree(client_list)
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["GET"])
    def search_role_users(self, request):
        _first, _max = UserManage.get_first_and_max(request.query_params)
        kwargs = {
            "first": _first,
            "max": _max,
            "search": request.GET.get("search", ""),
        }
        data = RoleManage().role_users(kwargs, request.GET.get("role_id"))
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["GET"])
    def get_all_menus(self, request):
        client_id = request.GET.get("client_id")
        data = RoleManage().get_all_menus(client_id, is_superuser=True)
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["GET"])
    def get_role_menus(self, request):
        policy_id = request.GET.get("policy_id")
        client_id = request.GET.get("id")
        data = RoleManage().role_menus(client_id, policy_id)
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    def create_role(self, request):
        data = RoleManage().role_create(request.data)
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    def delete_role(self, request):
        policy_id = request.data.get("policy_id")
        policy_name = request.data.get("display_name")
        client_id = request.data.get("id")
        role_name = request.data.get("role_name")
        try:
            RoleManage().role_delete(client_id, policy_id, policy_name, role_name)
        except Exception as e:
            return JsonResponse({"result": False, "message": str(e)})
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    def update_role(self, request):
        client_id = request.data.get("id")
        role_id = request.data.get("role_id")
        policy_id = request.data.get("policy_id")
        policy_name = request.data.get("policy_name")
        RoleManage().role_update(client_id, policy_id, policy_name, role_id)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    def add_user(self, request):
        pk = request.data.get("role_id")
        user_ids = request.data.get("user_ids")
        RoleManage().role_add_user(pk, user_ids)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    def delete_user(self, request):
        pk = request.data.get("role_id")
        user_ids = request.data.get("user_ids")
        RoleManage().role_remove_user(pk, user_ids)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    def assign_groups(self, request):
        pk = request.data.get("role_id")
        RoleManage().role_add_groups(request.data, pk)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    def unassign_groups(self, request):
        pk = request.data.get("role_id")
        RoleManage().role_remove_groups(request.data, pk)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["GET"])
    def get_groups_by_role(self, request):
        data = RoleManage().role_groups(request.GET.get("role_name"))
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    def set_role_menus(self, request):
        params = request.data
        policy_id = params.get("policy_id")
        policy_name = params.get("policy_name")
        client_id = params.get("id")
        menus = params.get("menus")
        RoleManage().set_role_menus(policy_id, menus, policy_name, client_id)
        return JsonResponse({"result": True})
