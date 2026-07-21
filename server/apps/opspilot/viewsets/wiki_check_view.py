from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import CheckItem, WikiDecisionRule
from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer
from apps.opspilot.services.wiki.check_service import close_incomplete_open_decision, decide_check
from apps.opspilot.services.wiki.decision_service import revoke_rule as revoke_decision_rule
from apps.opspilot.viewsets.wiki_team_scope import WikiTeamScopeMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation

_SEMANTIC_CHECK_TYPES = frozenset(("cannot_merge", "material_update", "duplicate", "conflict"))


class WikiCheckItemViewSet(WikiTeamScopeMixin, AuthViewSet):
    """只暴露需要人工介入的语义决策，并统一执行团队隔离。"""

    queryset = CheckItem.objects.filter(check_type__in=_SEMANTIC_CHECK_TYPES).order_by("-id")
    serializer_class = CheckItemSerializer

    @staticmethod
    def _semantic_action_error():
        return JsonResponse(
            {"result": False, "message": "通用审批接口已停用，请使用 decide 接口"},
            status=410,
        )

    ordering = ("-id",)

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST", detail="检查项只能由系统决策流程创建")

    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset().prefetch_related("decision_rules")
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        for check in queryset.filter(status="open").iterator(chunk_size=100):
            close_incomplete_open_decision(check)
        status_filter = request.GET.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        check_type = request.GET.get("check_type")
        if check_type:
            queryset = queryset.filter(check_type=check_type)
        assignee = request.GET.get("assignee")
        decision_only = request.GET.get("decision_only")
        if decision_only in ("1", "true", "yes"):
            queryset = queryset.filter(check_type__in=("cannot_merge", "material_update", "duplicate", "conflict"))
        decision_view = request.GET.get("view")
        if decision_view == "pending":
            queryset = queryset.filter(status="open")
        elif decision_view == "processed":
            queryset = queryset.filter(status__in=("resolved", "dismissed", "auto_resolved"))
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
        check = self.get_object()
        if close_incomplete_open_decision(check):
            check.refresh_from_db()
        return JsonResponse({"result": True, "data": self.get_serializer(check).data})

    @action(methods=["POST"], detail=True)
    def accept(self, request, pk=None):
        """兼容旧客户端：通用接受入口已停用。"""
        return self._semantic_action_error()

    @action(methods=["POST"], detail=True)
    def reject(self, request, pk=None):
        """兼容旧客户端：通用拒绝入口已停用。"""
        return self._semantic_action_error()

    @action(methods=["POST"], detail=True)
    def merge(self, request, pk=None):
        """兼容旧客户端：旧合并入口已停用。"""
        return self._semantic_action_error()

    @action(methods=["POST"], detail=True)
    def resolve(self, request, pk=None):
        """兼容旧客户端：通用处理入口已停用。"""
        return self._semantic_action_error()

    @action(methods=["POST"], detail=False)
    def batch_accept(self, request):
        """兼容旧客户端：批量接受入口已停用。"""
        return self._semantic_action_error()

    @action(methods=["POST"], detail=False)
    def batch_reject(self, request):
        """兼容旧客户端：批量拒绝入口已停用。"""
        return self._semantic_action_error()

    @action(methods=["POST"], detail=False)
    def batch_resolve(self, request):
        """兼容旧客户端：批量处理入口已停用。"""
        return self._semantic_action_error()

    @staticmethod
    def _parse_assignee_due(request):
        """解析分配/延期参数:assignee/due_at 可单独或同时提供;空值表示清除。"""
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

    @action(methods=["POST"], detail=True, url_path="decide")
    def decide(self, request, pk=None):
        """执行知识冲突或页面身份的语义化决策。"""
        check = self.get_object()
        action_value = (request.data.get("action") or "").strip()
        if not action_value:
            return JsonResponse(
                {"result": False, "message": "action 不能为空"},
                status=400,
            )
        body = request.data.get("body") or ""
        material = None
        material_id = request.data.get("material_id")
        if material_id not in (None, ""):
            if type(material_id) is not int or material_id <= 0:
                return JsonResponse(
                    {"result": False, "message": "material_id 必须为正整数"},
                    status=400,
                )
            from apps.opspilot.models import Material

            material = Material.objects.filter(
                id=material_id,
                knowledge_base=check.knowledge_base,
            ).first()
            if not material:
                return JsonResponse(
                    {
                        "result": False,
                        "message": f"material_id={material_id} 不存在或不属于同一知识库",
                    },
                    status=400,
                )
        try:
            rule = decide_check(
                check,
                action=action_value,
                operator=getattr(request.user, "username", ""),
                body=body,
                material=material,
            )
        except ValueError as exc:
            return JsonResponse({"result": False, "message": str(exc)}, status=400)
        check.refresh_from_db()
        if check.status == "auto_resolved":
            log_operation(
                request,
                "execute",
                "opspilot",
                f"自动关闭已失效 Wiki 决策(检查#{check.id})",
            )
            return JsonResponse(
                {
                    "result": False,
                    "message": "审批上下文已失效，系统已自动关闭该待决策项",
                    "data": {"check": self.get_serializer(check).data},
                },
                status=409,
            )
        log_operation(
            request,
            "execute",
            "opspilot",
            f"决策检查项(检查#{check.id}): action={action_value}, 规则={getattr(rule, 'id', None)}",
        )
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "check": self.get_serializer(check).data,
                    "rule_id": getattr(rule, "id", None),
                },
            }
        )

    @action(methods=["POST"], detail=True, url_path="revoke_rule")
    def revoke_rule(self, request, pk=None):
        """撤销当前处理记录关联的规则，不回滚已生效知识。"""
        check = self.get_object()
        raw_rule_id = request.data.get("rule_id")
        rules = WikiDecisionRule.objects.filter(knowledge_base=check.knowledge_base).order_by("-id")
        if raw_rule_id not in (None, ""):
            try:
                rule_id = int(raw_rule_id)
            except (TypeError, ValueError):
                return JsonResponse(
                    {"result": False, "message": "rule_id 必须为整数"},
                    status=400,
                )
            rule = rules.filter(id=rule_id).first()
        else:
            rule = rules.filter(source_check=check).first()
            if rule is None and check.decision_key:
                rule = rules.filter(decision_key=check.decision_key).first()
        if rule is None:
            return JsonResponse(
                {"result": False, "message": "未找到该处理记录关联的决策规则"},
                status=400,
            )
        if rule.source_check_id != check.id and (not check.decision_key or rule.decision_key != check.decision_key):
            return JsonResponse(
                {"result": False, "message": "规则不属于该处理记录"},
                status=400,
            )
        revoke_decision_rule(
            rule,
            reason=(request.data.get("reason") or "").strip(),
            operator=getattr(request.user, "username", ""),
        )
        check.refresh_from_db()
        log_operation(
            request,
            "execute",
            "opspilot",
            f"撤销 Wiki 决策规则(规则#{rule.id}, 检查#{check.id})",
        )
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "check": self.get_serializer(check).data,
                    "rule_id": rule.id,
                },
            }
        )


WikiCheckViewSet = WikiCheckItemViewSet
