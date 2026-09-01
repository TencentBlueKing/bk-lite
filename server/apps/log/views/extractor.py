from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.core.utils.permission_utils import get_instance_permissions, get_permissions_rules
from apps.log.constants.permission import PermissionConstants
from apps.log.models import CollectInstance, CollectType, LogExtractor
from apps.log.serializers.extractor import LogExtractorSerializer
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.services.log_extractor.publication import get_publication_status, retry_publication
from apps.log.services.log_extractor.rules import (
    create_rule,
    create_type_rule,
    delete_rule,
    load_samples,
    load_type_samples,
    preview_rule,
    preview_type_rule,
    reorder_rules,
    reorder_type_rules,
    resolve_type_scope,
    update_rule,
)
from apps.log.services.log_extractor.semantics import RuleExecutionBusyError, RuleExecutionLimitError, RuleExecutionTimeoutError
from apps.system_mgmt.utils.operation_log_utils import log_operation

TYPE_SCOPE_VIEW_PERMISSIONS = frozenset({"integration_configure-View", "integration_list-View"})
TYPE_SCOPE_WRITE_PERMISSIONS = frozenset({"integration_configure-Add"})


class LogExtractorViewSet(ViewSet):
    def _authorize_instance(self, request, instance_id, required: str) -> CollectInstance:
        if not instance_id:
            raise ValidationError({"collect_instance": "采集实例必填"})
        instance = (
            CollectInstance.objects.filter(pk=str(instance_id))
            .select_related("collect_type")
            .prefetch_related("collectinstanceorganization_set")
            .first()
        )
        if not instance:
            raise NotFound()
        try:
            scope = LogAccessScopeService.get_data_scope(request)
        except ValueError as exc:
            raise PermissionDenied(str(exc)) from exc
        organizations = {relation.organization for relation in instance.collectinstanceorganization_set.all()}
        if not organizations.intersection(scope.data_team_ids):
            raise NotFound()
        if scope.is_superuser:
            return instance
        permission_result = get_permissions_rules(
            request.user,
            scope.current_team,
            "log",
            PermissionConstants.INSTANCE_MODULE,
            include_children=scope.include_children,
        )
        permission_data = permission_result.get("data", {}) if isinstance(permission_result, dict) else {}
        permissions = get_instance_permissions(instance.collect_type_id, instance.pk, organizations, permission_data, list(scope.data_team_ids))
        if required not in permissions:
            raise PermissionDenied()
        return instance

    @staticmethod
    def _user_log_permissions(request) -> set[str]:
        user_permissions = getattr(request.user, "permission", set())
        if isinstance(user_permissions, dict):
            return set(user_permissions.get("log") or [])
        if isinstance(user_permissions, set):
            return user_permissions
        return set()

    def _authorize_type_scope(self, request, collect_type_name, required: str) -> CollectType:
        collect_type = resolve_type_scope(collect_type_name)
        try:
            LogAccessScopeService.get_data_scope(request)
        except ValueError as exc:
            raise PermissionDenied(str(exc)) from exc
        if getattr(request.user, "is_superuser", False):
            return collect_type
        perms = self._user_log_permissions(request)
        needed = TYPE_SCOPE_WRITE_PERMISSIONS if required == "Operate" else TYPE_SCOPE_VIEW_PERMISSIONS
        if not perms.intersection(needed):
            raise PermissionDenied()
        return collect_type

    def _exclusive_scope(self, payload):
        instance_id = payload.get("collect_instance")
        collect_type_name = payload.get("collect_type")
        has_instance = bool(instance_id)
        has_type = bool(collect_type_name)
        if has_instance == has_type:
            raise ValidationError({"collect_instance": "必须且只能提供采集实例或采集类型之一"})
        return instance_id, collect_type_name

    def _authorize_scope(self, request, payload, required: str):
        instance_id, collect_type_name = self._exclusive_scope(payload)
        if instance_id:
            return self._authorize_instance(request, instance_id, required), None
        return None, self._authorize_type_scope(request, collect_type_name, required)

    def _get_rule(self, request, pk, required: str) -> LogExtractor:
        rule = (
            LogExtractor.objects.filter(pk=pk)
            .select_related("collect_instance__collect_type", "collect_type")
            .first()
        )
        if not rule or (not rule.collect_instance_id and not rule.collect_type_id):
            raise NotFound()
        if rule.collect_instance_id:
            self._authorize_instance(request, rule.collect_instance_id, required)
        else:
            self._authorize_type_scope(request, rule.collect_type.name, required)
        return rule

    @staticmethod
    def _payload(rule, generation=None):
        payload = {"resource": LogExtractorSerializer(rule).data, "publication": get_publication_status()}
        if generation is not None:
            payload["generation"] = generation
        return payload

    @staticmethod
    def _scope_log(instance, collect_type) -> str:
        if instance is not None:
            return f"instance={instance.pk}"
        return f"collect_type={collect_type.name}"

    def list(self, request):
        instance, collect_type = self._authorize_scope(request, request.query_params, "View")
        if instance is not None:
            rules = LogExtractor.objects.filter(collect_instance=instance).select_related("collect_type").order_by("sort_order", "id")
        else:
            rules = LogExtractor.objects.filter(collect_type=collect_type, collect_instance__isnull=True).select_related("collect_type").order_by("sort_order", "id")
        can_operate = False
        try:
            self._authorize_scope(request, request.query_params, "Operate")
            can_operate = True
        except PermissionDenied:
            can_operate = False
        return Response(
            {
                "items": LogExtractorSerializer(rules, many=True).data,
                "publication": get_publication_status(),
                "can_operate": can_operate,
            }
        )

    def retrieve(self, request, pk=None):
        return Response(self._payload(self._get_rule(request, pk, "View")))

    def create(self, request):
        instance, collect_type = self._authorize_scope(request, request.data, "Operate")
        serializer = LogExtractorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("collect_instance", None)
        data.pop("collect_type", None)
        data.pop("_collect_type_name", None)
        if instance is not None:
            rule, generation = create_rule(instance, data, request.user)
        else:
            rule, generation = create_type_rule(collect_type, data, request.user)
        log_operation(
            request,
            "create",
            "log",
            f"新增日志提取器: {self._scope_log(instance, collect_type)}, rule={rule.pk}, name={rule.name}, generation={generation}",
        )
        return Response(self._payload(rule, generation), status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        rule = self._get_rule(request, pk, "Operate")
        serializer = LogExtractorSerializer(rule, data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("_collect_type_name", None)
        data.pop("collect_type", None)
        rule, generation = update_rule(rule, data, request.user)
        log_operation(
            request,
            "update",
            "log",
            f"编辑日志提取器: instance={rule.collect_instance_id}, collect_type={rule.collect_type_id}, rule={rule.pk}, name={rule.name}, generation={generation}",
        )
        return Response(self._payload(rule, generation))

    def partial_update(self, request, pk=None):
        rule = self._get_rule(request, pk, "Operate")
        serializer = LogExtractorSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("_collect_type_name", None)
        data.pop("collect_type", None)
        rule, generation = update_rule(rule, data, request.user)
        log_operation(
            request,
            "update",
            "log",
            f"编辑日志提取器: instance={rule.collect_instance_id}, collect_type={rule.collect_type_id}, rule={rule.pk}, name={rule.name}, generation={generation}",
        )
        return Response(self._payload(rule, generation))

    def destroy(self, request, pk=None):
        rule = self._get_rule(request, pk, "Operate")
        instance_id, collect_type_id, rule_id, name = rule.collect_instance_id, rule.collect_type_id, rule.pk, rule.name
        generation = delete_rule(rule)
        log_operation(
            request,
            "delete",
            "log",
            f"删除日志提取器: instance={instance_id}, collect_type={collect_type_id}, rule={rule_id}, name={name}, generation={generation}",
        )
        return Response({"generation": generation, "publication": get_publication_status()})

    @action(methods=("post",), detail=False)
    def reorder(self, request):
        instance, collect_type = self._authorize_scope(request, request.data, "Operate")
        if instance is not None:
            generation = reorder_rules(instance, request.data.get("ids"))
        else:
            generation = reorder_type_rules(collect_type, request.data.get("ids"))
        log_operation(
            request,
            "update",
            "log",
            f"调整日志提取器顺序: {self._scope_log(instance, collect_type)}, generation={generation}",
        )
        return Response({"generation": generation, "publication": get_publication_status()})

    def _preview_errors(self, exc):
        if isinstance(exc, RuleExecutionBusyError):
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": "1"})
        if isinstance(exc, RuleExecutionTimeoutError):
            return Response(
                {"detail": str(exc), "data": {"error_code": "log_extractor_preview_timeout"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(exc, RuleExecutionLimitError):
            return Response(
                {"detail": str(exc), "data": {"error_code": "log_extractor_preview_too_large"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    @action(methods=("post",), detail=False)
    def preview(self, request):
        instance, collect_type = self._authorize_scope(request, request.data, "View")
        try:
            if instance is not None:
                result = preview_rule(instance, request.data.get("event"), request.data.get("draft"), request.data.get("rule_id"))
            else:
                result = preview_type_rule(collect_type, request.data.get("event"), request.data.get("draft"), request.data.get("rule_id"))
        except (RuleExecutionBusyError, RuleExecutionTimeoutError, RuleExecutionLimitError) as exc:
            return self._preview_errors(exc)
        except ValueError as exc:
            raise ValidationError({"rule": str(exc)}) from exc
        return Response(result)

    @action(methods=("get",), detail=False)
    def samples(self, request):
        instance, collect_type = self._authorize_scope(request, request.query_params, "View")
        try:
            if instance is not None:
                return Response(load_samples(instance, request.query_params.get("limit")))
            return Response(load_type_samples(collect_type, request.query_params.get("limit")))
        except ValueError as exc:
            raise ValidationError({"limit": str(exc)}) from exc

    @action(methods=("post",), detail=False)
    def retry(self, request):
        instance, collect_type = self._authorize_scope(request, request.data, "Operate")
        generation = retry_publication()
        if generation is None:
            return Response({"detail": "当前 generation 已发布"}, status=status.HTTP_409_CONFLICT)
        log_operation(
            request,
            "execute",
            "log",
            f"重试日志提取器发布: {self._scope_log(instance, collect_type)}, generation={generation}",
        )
        return Response({"generation": generation, "publication": get_publication_status()})

    @action(methods=("get",), detail=False)
    def publication_status(self, request):
        self._authorize_scope(request, request.query_params, "View")
        return Response(get_publication_status())
