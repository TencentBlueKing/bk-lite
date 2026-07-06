from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import CheckItem
from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer
from apps.opspilot.services.wiki.check_service import accept_candidate, merge_duplicate_check, reject_candidate, resolve_check
from apps.system_mgmt.utils.operation_log_utils import log_operation


class WikiCheckItemViewSet(AuthViewSet):
    """检查与审核:列出风险/检查事项,接受/拒绝候选版本。"""

    queryset = CheckItem.objects.all().order_by("-id")
    serializer_class = CheckItemSerializer
    ordering = ("-id",)
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        status_filter = request.GET.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        check_type = request.GET.get("check_type")
        if check_type:
            queryset = queryset.filter(check_type=check_type)
        assignee = request.GET.get("assignee")
        if assignee:
            if assignee == "__unassigned__":
                queryset = queryset.filter(assignee="")
            elif assignee == "__mine__":
                queryset = queryset.filter(assignee=getattr(request.user, "username", ""))
            else:
                queryset = queryset.filter(assignee=assignee)
        action_type = request.GET.get("action_type")
        if action_type:
            queryset = queryset.filter(action_type=action_type)
        overdue = request.GET.get("overdue")
        if overdue in ("1", "true", "yes"):
            from django.utils import timezone

            queryset = queryset.filter(due_at__lt=timezone.now())
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = max(int(request.GET.get("page_size", 20)), 1)
        except (TypeError, ValueError):
            page, page_size = 1, 20
        total = queryset.count()
        page_items = queryset[(page - 1) * page_size : (page - 1) * page_size + page_size]
        return JsonResponse({"result": True, "data": {"count": total, "items": self.get_serializer(page_items, many=True).data}})

    def retrieve(self, request, *args, **kwargs):
        return JsonResponse({"result": True, "data": self.get_serializer(self.get_object()).data})

    def _parse_ids(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return None, JsonResponse({"result": False, "message": "ids 不能为空"}, status=400)

        parsed_ids = []
        seen = set()
        for raw_id in ids:
            try:
                check_id = int(raw_id)
            except (TypeError, ValueError):
                return None, JsonResponse({"result": False, "message": "ids 必须为整数列表"}, status=400)
            if check_id not in seen:
                parsed_ids.append(check_id)
                seen.add(check_id)
        return parsed_ids, None

    def _open_checks_by_id(self, ids):
        return {check.id: check for check in self.get_queryset().filter(id__in=ids, status="open").select_related("candidate_version")}

    @action(methods=["POST"], detail=True)
    def accept(self, request, pk=None):
        """接受候选版本:置为当前有效版本并关闭检查。"""
        check = self.get_object()
        if not check.candidate_version_id:
            return JsonResponse({"result": False, "message": "该检查无候选版本"}, status=400)
        accept_candidate(check, operator=getattr(request.user, "username", ""))
        log_operation(request, "execute", "opspilot", f"接受候选版本(检查#{check.id})")
        return JsonResponse({"result": True, "data": self.get_serializer(check).data})

    @action(methods=["POST"], detail=True)
    def reject(self, request, pk=None):
        """拒绝候选版本:丢弃候选,当前有效版本不变。"""
        check = self.get_object()
        reject_candidate(check, operator=getattr(request.user, "username", ""))
        log_operation(request, "execute", "opspilot", f"拒绝候选版本(检查#{check.id})")
        return JsonResponse({"result": True, "data": self.get_serializer(check).data})

    @action(methods=["POST"], detail=True)
    def merge(self, request, pk=None):
        """合并重复/同义页面:仅允许 duplicate 检查项。"""
        check = self.get_object()
        try:
            merge_duplicate_check(check, operator=getattr(request.user, "username", ""))
        except ValueError as exc:
            return JsonResponse({"result": False, "message": str(exc)}, status=400)
        check.refresh_from_db()
        log_operation(request, "execute", "opspilot", f"合并重复知识页(检查#{check.id})")
        return JsonResponse({"result": True, "data": self.get_serializer(check).data})

    @action(methods=["POST"], detail=True)
    def resolve(self, request, pk=None):
        """标记扫描/洞察类检查项已处理,并记录处理结果。"""
        check = self.get_object()
        try:
            resolve_check(
                check,
                operator=getattr(request.user, "username", ""),
                note=(request.data.get("note") or "").strip(),
            )
        except ValueError as exc:
            return JsonResponse({"result": False, "message": str(exc)}, status=400)
        check.refresh_from_db()
        log_operation(request, "execute", "opspilot", f"标记检查项已处理(检查#{check.id})")
        return JsonResponse({"result": True, "data": self.get_serializer(check).data})

    @action(methods=["POST"], detail=False)
    def batch_accept(self, request):
        """批量接受候选版本:无候选/非 open/不存在的检查项会被跳过。"""
        ids, error = self._parse_ids(request)
        if error:
            return error

        checks_by_id = self._open_checks_by_id(ids)
        operator = getattr(request.user, "username", "")
        accepted = 0
        skipped_ids = []
        for check_id in ids:
            check = checks_by_id.get(check_id)
            if not check or not check.candidate_version_id:
                skipped_ids.append(check_id)
                continue
            accept_candidate(check, operator=operator)
            accepted += 1

        log_operation(request, "execute", "opspilot", f"批量接受候选版本({accepted}项)")
        return JsonResponse({"result": True, "data": {"accepted": accepted, "skipped": len(skipped_ids), "skipped_ids": skipped_ids}})

    @action(methods=["POST"], detail=False)
    def batch_reject(self, request):
        """批量拒绝/忽略检查项:仅关闭选中的 open 检查项。"""
        ids, error = self._parse_ids(request)
        if error:
            return error

        checks_by_id = self._open_checks_by_id(ids)
        operator = getattr(request.user, "username", "")
        rejected = 0
        skipped_ids = []
        for check_id in ids:
            check = checks_by_id.get(check_id)
            if not check:
                skipped_ids.append(check_id)
                continue
            reject_candidate(check, operator=operator)
            rejected += 1

        log_operation(request, "execute", "opspilot", f"批量拒绝/忽略检查项({rejected}项)")
        return JsonResponse({"result": True, "data": {"rejected": rejected, "skipped": len(skipped_ids), "skipped_ids": skipped_ids}})

    @action(methods=["POST"], detail=False)
    def batch_resolve(self, request):
        """批量标记扫描/洞察类检查项已处理:候选/非 open/不存在的检查项会被跳过。"""
        ids, error = self._parse_ids(request)
        if error:
            return error

        checks_by_id = self._open_checks_by_id(ids)
        operator = getattr(request.user, "username", "")
        note = (request.data.get("note") or "").strip()
        resolved = 0
        skipped_ids = []
        for check_id in ids:
            check = checks_by_id.get(check_id)
            if not check or check.candidate_version_id:
                skipped_ids.append(check_id)
                continue
            resolve_check(check, operator=operator, note=note)
            resolved += 1

        log_operation(request, "execute", "opspilot", f"批量标记检查项已处理({resolved}项)")
        return JsonResponse({"result": True, "data": {"resolved": resolved, "skipped": len(skipped_ids), "skipped_ids": skipped_ids}})

    @staticmethod
    def _parse_assignee_due(request):
        """解析分配/延期参数:assignee/due_at 可单独或同时提供;空值表示清除。"""
        from django.utils.dateparse import parse_datetime

        raw_assignee = request.data.get("assignee")
        raw_due = request.data.get("due_at")
        raw_action = request.data.get("action_type")
        fields = {}
        if raw_assignee is not None:
            fields["assignee"] = str(raw_assignee).strip()
        if raw_due is not None:
            value = str(raw_due).strip()
            if not value:
                fields["due_at"] = None
            else:
                parsed = parse_datetime(value)
                if parsed is None:
                    return None, JsonResponse({"result": False, "message": "due_at 必须为 ISO 8601 时间字符串"}, status=400)
                fields["due_at"] = parsed
        if raw_action is not None:
            fields["action_type"] = str(raw_action).strip()
        return fields, None

    @action(methods=["POST"], detail=True)
    def assign(self, request, pk=None):
        """分配/延期/动作类型:可单独或同时更新 assignee、due_at、action_type。空值表示清除。"""
        check = self.get_object()
        fields, error = self._parse_assignee_due(request)
        if error:
            return error
        if not fields:
            return JsonResponse({"result": False, "message": "请至少提供 assignee / due_at / action_type 之一"}, status=400)
        for name, value in fields.items():
            setattr(check, name, value)
        check.save(update_fields=list(fields.keys()) + ["updated_at"])
        log_operation(
            request,
            "execute",
            "opspilot",
            f"分配检查项(检查#{check.id}): {', '.join(f'{k}={v!r}' for k, v in fields.items())}",
        )
        return JsonResponse({"result": True, "data": self.get_serializer(check).data})
