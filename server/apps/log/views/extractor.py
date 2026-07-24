from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.core.utils.permission_utils import get_instance_permissions, get_permissions_rules
from apps.log.constants.permission import PermissionConstants
from apps.log.models import CollectInstance, LogExtractor
from apps.log.serializers.extractor import LogExtractorSerializer
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.services.log_extractor.publication import get_publication_status, retry_publication
from apps.log.services.log_extractor.rules import create_rule, delete_rule, load_samples, preview_rule, reorder_rules, update_rule
from apps.system_mgmt.utils.operation_log_utils import log_operation


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

    def _get_rule(self, request, pk, required: str) -> LogExtractor:
        rule = LogExtractor.objects.filter(pk=pk, collect_instance__isnull=False).select_related("collect_instance__collect_type").first()
        if not rule:
            raise NotFound()
        self._authorize_instance(request, rule.collect_instance_id, required)
        return rule

    @staticmethod
    def _payload(rule, generation=None):
        payload = {"resource": LogExtractorSerializer(rule).data, "publication": get_publication_status()}
        if generation is not None:
            payload["generation"] = generation
        return payload

    def list(self, request):
        instance = self._authorize_instance(request, request.query_params.get("collect_instance"), "View")
        rules = LogExtractor.objects.filter(collect_instance=instance).order_by("sort_order", "id")
        return Response({"items": LogExtractorSerializer(rules, many=True).data, "publication": get_publication_status()})

    def retrieve(self, request, pk=None):
        return Response(self._payload(self._get_rule(request, pk, "View")))

    def create(self, request):
        instance = self._authorize_instance(request, request.data.get("collect_instance"), "Operate")
        serializer = LogExtractorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("collect_instance", None)
        rule, generation = create_rule(instance, data, request.user)
        log_operation(
            request,
            "create",
            "log",
            f"新增日志提取器: instance={instance.pk}, rule={rule.pk}, name={rule.name}, generation={generation}",
        )
        return Response(self._payload(rule, generation), status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        rule = self._get_rule(request, pk, "Operate")
        serializer = LogExtractorSerializer(rule, data=request.data)
        serializer.is_valid(raise_exception=True)
        rule, generation = update_rule(rule, dict(serializer.validated_data), request.user)
        log_operation(
            request,
            "update",
            "log",
            f"编辑日志提取器: instance={rule.collect_instance_id}, rule={rule.pk}, name={rule.name}, generation={generation}",
        )
        return Response(self._payload(rule, generation))

    def partial_update(self, request, pk=None):
        rule = self._get_rule(request, pk, "Operate")
        serializer = LogExtractorSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rule, generation = update_rule(rule, dict(serializer.validated_data), request.user)
        log_operation(
            request,
            "update",
            "log",
            f"编辑日志提取器: instance={rule.collect_instance_id}, rule={rule.pk}, name={rule.name}, generation={generation}",
        )
        return Response(self._payload(rule, generation))

    def destroy(self, request, pk=None):
        rule = self._get_rule(request, pk, "Operate")
        instance_id, rule_id, name = rule.collect_instance_id, rule.pk, rule.name
        generation = delete_rule(rule)
        log_operation(
            request,
            "delete",
            "log",
            f"删除日志提取器: instance={instance_id}, rule={rule_id}, name={name}, generation={generation}",
        )
        return Response({"generation": generation, "publication": get_publication_status()})

    @action(methods=("post",), detail=False)
    def reorder(self, request):
        instance = self._authorize_instance(request, request.data.get("collect_instance"), "Operate")
        generation = reorder_rules(instance, request.data.get("ids"))
        log_operation(
            request,
            "update",
            "log",
            f"调整日志提取器顺序: instance={instance.pk}, generation={generation}",
        )
        return Response({"generation": generation, "publication": get_publication_status()})

    @action(methods=("post",), detail=False)
    def preview(self, request):
        instance = self._authorize_instance(request, request.data.get("collect_instance"), "View")
        try:
            result = preview_rule(instance, request.data.get("event"), request.data.get("draft"), request.data.get("rule_id"))
        except ValueError as exc:
            raise ValidationError({"rule": str(exc)}) from exc
        return Response(result)

    @action(methods=("get",), detail=False)
    def samples(self, request):
        instance = self._authorize_instance(request, request.query_params.get("collect_instance"), "View")
        try:
            return Response(load_samples(instance, request.query_params.get("limit")))
        except ValueError as exc:
            raise ValidationError({"limit": str(exc)}) from exc

    @action(methods=("post",), detail=False)
    def retry(self, request):
        instance = self._authorize_instance(request, request.data.get("collect_instance"), "Operate")
        generation = retry_publication()
        if generation is None:
            return Response({"detail": "当前 generation 已发布"}, status=status.HTTP_409_CONFLICT)
        log_operation(
            request,
            "execute",
            "log",
            f"重试日志提取器发布: instance={instance.pk}, generation={generation}",
        )
        return Response({"generation": generation, "publication": get_publication_status()})

    @action(methods=("get",), detail=False)
    def publication_status(self, request):
        self._authorize_instance(request, request.query_params.get("collect_instance"), "View")
        return Response(get_publication_status())
