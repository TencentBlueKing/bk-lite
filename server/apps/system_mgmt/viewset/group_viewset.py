from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.system_mgmt.services.group_manage import GroupManage


class GroupViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["GET"])
    def search_group_list(self, request):
        data = GroupManage().group_list(request.GET.dict())
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["GET"])
    def get_detail(self, request):
        data = GroupManage().group_retrieve(request.GET.get("group_id"))
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    def create_group(self, request):
        data = GroupManage().group_create(request.data)
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    def update_group(self, request):
        GroupManage().group_update(request.data)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    def delete_groups(self, request):
        GroupManage().group_delete(request.data)
        return JsonResponse({"result": True})

    #
    # @action(detail=False, methods=["GET"])
    # def get_users_in_group(self, request):
    #     pk = request.GET.get("group_id")
    #     data = GroupManage().group_users(pk)
    #     return JsonResponse({"result": True, "data": data})
    #
    # @action(detail=False, methods=["POST"])
    # def assign_group_users(self, request):
    #     pk = request.data.get("group_id")
    #     data = GroupManage().group_add_users(request.data, pk)
    #     return JsonResponse({"result": True, "data": data})
    #
    # @action(detail=False, methods=["POST"])
    # def unassigned_group_users(self, request):
    #     pk = request.data.get("group_id")
    #     data = GroupManage().group_remove_users(request.data, pk)
    #     return JsonResponse({"result": True, "data": data})
    #
    # @action(detail=False, methods=["GET"])
    # def get_roles_in_group(self, request):
    #     pk = request.GET.get("group_id")
    #     data = GroupManage().group_roles(pk)
    #     return JsonResponse({"result": True, "data": data})
    #
    # @action(detail=False, methods=["POST"])
    # def assign_group_roles(self, request):
    #     pk = request.data.get("group_id")
    #     data = GroupManage().group_add_roles(request.data, pk)
    #     return JsonResponse({"result": True, "data": data})
    #
    # @action(detail=False, methods=["POST"])
    # def unassigned_group_roles(self, request):
    #     pk = request.data.get("group_id")
    #     data = GroupManage().group_remove_roles(request.data, pk)
    #     return JsonResponse({"result": True, "data": data})
