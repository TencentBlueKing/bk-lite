import logging

from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import WikiDirectory
from apps.opspilot.services.wiki.active_generation_query_service import ActiveGenerationReadError, directory_page_counts
from apps.opspilot.services.wiki.directory_operation_service import execute_directory_operation, preview_directory_operation
from apps.opspilot.services.wiki.directory_service import DirectoryServiceError
from apps.opspilot.services.wiki.structure_service import StructureServiceError, get_structure, save_structure
from apps.opspilot.viewsets.wiki_team_scope import WikiTeamScopeMixin

UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__"
logger = logging.getLogger("opspilot")


def _log_structure_conflict(knowledge_base, error):
    if error.status_code == 409:
        logger.warning(
            "wiki_structure_conflict kb=%s code=%s retryable=%s",
            knowledge_base.pk,
            error.code,
            error.retryable,
        )


def _active_generation_conflict(error):
    return JsonResponse(
        {
            "result": False,
            "message": str(error),
            "code": error.code,
            "details": error.details,
        },
        status=409,
    )


def _directory_operation_error(error):
    return JsonResponse(
        {
            "result": False,
            "message": str(error),
            "code": error.code,
            "retryable": error.retryable,
            "details": error.details,
        },
        status=error.status_code,
    )


class WikiDirectoryViewSet(WikiTeamScopeMixin, AuthViewSet):
    """知识目录读取与版本化结构治理入口。"""

    queryset = WikiDirectory.objects.all().order_by("sort_order", "id")
    team_scope_field = "knowledge_base_id"
    http_method_names = ["get", "post", "put", "head", "options"]

    def _structure_knowledge_base(self, request):
        raw_id = request.query_params.get("knowledge_base")
        if raw_id in (None, ""):
            return None, JsonResponse(
                {"result": False, "message": "knowledge_base 必填", "code": "knowledge_base_required"},
                status=400,
            )
        try:
            knowledge_base_id = int(raw_id)
        except (TypeError, ValueError):
            return None, JsonResponse(
                {"result": False, "message": "knowledge_base 必须为整数", "code": "knowledge_base_invalid"},
                status=400,
            )
        knowledge_base = self.accessible_knowledge_base_or_none(knowledge_base_id)
        if knowledge_base is None:
            return None, JsonResponse(
                {"result": False, "message": "知识库不存在", "code": "knowledge_base_not_found"},
                status=404,
            )
        return knowledge_base, None

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=False)
    def structure(self, request):
        knowledge_base, error_response = self._structure_knowledge_base(request)
        if error_response is not None:
            return error_response

        try:
            data = get_structure(knowledge_base)
        except StructureServiceError as error:
            _log_structure_conflict(knowledge_base, error)
            return JsonResponse(
                {
                    "result": False,
                    "message": str(error),
                    "code": error.code,
                    "retryable": error.retryable,
                    "details": error.details,
                },
                status=error.status_code,
            )

        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-Edit")
    @structure.mapping.put
    def update_structure(self, request):
        knowledge_base, error_response = self._structure_knowledge_base(request)
        if error_response is not None:
            return error_response

        user = getattr(request, "user", None)
        try:
            data = save_structure(
                knowledge_base,
                request.data,
                operator=getattr(user, "username", "") or "",
            )
        except StructureServiceError as error:
            _log_structure_conflict(knowledge_base, error)
            return JsonResponse(
                {
                    "result": False,
                    "message": str(error),
                    "code": error.code,
                    "retryable": error.retryable,
                    "details": error.details,
                },
                status=error.status_code,
            )

        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False)
    def operation_preview(self, request):
        knowledge_base, error_response = self._structure_knowledge_base(request)
        if error_response is not None:
            return error_response
        try:
            data = preview_directory_operation(
                knowledge_base,
                request.data,
            )
        except DirectoryServiceError as error:
            return _directory_operation_error(error)
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False)
    def operation_execute(self, request):
        knowledge_base, error_response = self._structure_knowledge_base(request)
        if error_response is not None:
            return error_response
        try:
            data = execute_directory_operation(
                knowledge_base,
                request.data,
                operator=(getattr(request.user, "username", "") or ""),
            )
        except DirectoryServiceError as error:
            return _directory_operation_error(error)
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=False)
    def tree(self, request):
        knowledge_base = self.accessible_knowledge_base_or_none(request.GET.get("knowledge_base"))
        if knowledge_base is None:
            return JsonResponse(
                {"result": False, "message": "knowledge_base 必填或知识库不存在"},
                status=400,
            )

        directories = list(
            WikiDirectory.objects.filter(
                knowledge_base=knowledge_base,
                status="active",
            )
            .values(
                "id",
                "key",
                "name",
                "description",
                "parent_id",
                "sort_order",
                "status",
                "origin",
                "accepts_pages",
            )
            .order_by("sort_order", "id")
        )
        tombstones = list(
            WikiDirectory.objects.filter(knowledge_base=knowledge_base)
            .exclude(status="active")
            .values("id", "key", "name", "status", "merged_into_id")
            .order_by("id")
        )
        try:
            direct_counts = directory_page_counts(knowledge_base, statuses=("active",))
        except ActiveGenerationReadError as error:
            return _active_generation_conflict(error)

        nodes = {}
        unclassified_directory_id = None
        for directory in directories:
            direct_page_count = direct_counts.get(directory["id"], 0)
            node = {
                **directory,
                "direct_page_count": direct_page_count,
                "total_page_count": direct_page_count,
                "children": [],
            }
            node["order"] = node.pop("sort_order")
            node["is_system"] = node.pop("origin") == "system"
            nodes[node["id"]] = node
            if node["key"] == UNCLASSIFIED_DIRECTORY_KEY:
                unclassified_directory_id = node["id"]

        roots = []
        for node in nodes.values():
            parent = nodes.get(node["parent_id"])
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)

        def populate_total_page_count(node):
            node["total_page_count"] = node["direct_page_count"] + sum(populate_total_page_count(child) for child in node["children"])
            return node["total_page_count"]

        for root in roots:
            populate_total_page_count(root)

        return JsonResponse(
            {
                "result": True,
                "data": {
                    "enabled": knowledge_base.directory_enabled,
                    "unclassified_directory_id": unclassified_directory_id,
                    "structure_revision_id": (knowledge_base.active_structure_revision_id),
                    "structure_version": (
                        knowledge_base.active_structure_revision.revision_no if knowledge_base.active_structure_revision_id else None
                    ),
                    "active_generation_id": knowledge_base.active_generation_id,
                    "directories": roots,
                    "tombstones": tombstones,
                },
            }
        )
