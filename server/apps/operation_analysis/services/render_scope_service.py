from __future__ import annotations

import os
import re

import jwt
from django.utils import timezone

from apps.core.backends import AuthBackend
from apps.operation_analysis.models.datasource_models import NameSpace
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportRenderToken,
)
from apps.system_mgmt.models import User as SystemUser
from apps.system_mgmt.nats.auth import build_user_authorization_context


class DashboardReportRenderScopeError(RuntimeError):
    pass


class DashboardReportRenderScopeService:
    TOKEN_TYPE = "dashboard_report_render"
    _RENDER_INPUT = re.compile(
        r"^(?:/api/v1)?/operation_analysis/api/dashboard_execution/(\d+)/render-input/$"
    )
    _DATASOURCE_QUERY = re.compile(
        r"^(?:/api/v1)?/operation_analysis/api/data_source/get_source_data/(\d+)/$"
    )
    _DATASOURCE_LIST = re.compile(
        r"^(?:/api/v1)?/operation_analysis/api/data_source/$"
    )
    _NAMESPACE_LIST = re.compile(
        r"^(?:/api/v1)?/operation_analysis/api/namespace/$"
    )
    _NETWORK_STATUS_TOPOLOGY = re.compile(
        r"^(?:/api/v1)?/operation_analysis/api/scene_widgets/network_status_topology/$"
    )

    @classmethod
    def decode_if_render(cls, token: str) -> dict | None:
        secret_key = os.getenv("SECRET_KEY")
        if not secret_key or not token:
            return None
        try:
            claims = jwt.decode(
                token,
                secret_key,
                algorithms=[os.getenv("JWT_ALGORITHM", "HS256")],
            )
        except Exception:
            return None
        return claims if claims.get("token_type") == cls.TOKEN_TYPE else None

    @classmethod
    def resolve_request_user(cls, request, claims: dict):
        """用创建者实时身份建立 request.user，不经过普通 verify_token。"""
        try:
            system_user = SystemUser.objects.get(
                username=claims.get("creator_username", ""),
                domain=claims.get("creator_domain", ""),
                disabled=False,
            )
        except (
            SystemUser.DoesNotExist,
            SystemUser.MultipleObjectsReturned,
        ):
            return None

        # build_user_authorization_context 期望 group_list 为 int ID 列表。
        original_groups = system_user.group_list
        system_user.group_list = sorted(cls._creator_team_ids(system_user))
        try:
            user_info = build_user_authorization_context(system_user)
        finally:
            system_user.group_list = original_groups

        rules: dict = {}
        team = getattr(request, "_api_current_team", None)
        if team is not None:
            try:
                from apps.rpc.system_mgmt import SystemMgmt

                loaded = SystemMgmt().get_user_rules(
                    str(team), system_user.username
                )
                if isinstance(loaded, dict):
                    rules = loaded
            except Exception:
                rules = {}
        return AuthBackend().set_user_info(request, user_info, rules)

    @staticmethod
    def _creator_team_ids(creator: SystemUser | None) -> set[int]:
        result: set[int] = set()
        for item in (getattr(creator, "group_list", None) or []):
            raw_id = item.get("id") if isinstance(item, dict) else item
            try:
                result.add(int(raw_id))
            except (TypeError, ValueError):
                continue
        return result

    @classmethod
    def assert_creator_still_in_execution_team(
        cls,
        *,
        creator_username: str,
        creator_domain: str,
        execution_team_id: int,
    ) -> None:
        creator = SystemUser.objects.filter(
            username=creator_username,
            domain=creator_domain,
            disabled=False,
        ).first()
        if execution_team_id not in cls._creator_team_ids(creator):
            raise DashboardReportRenderScopeError(
                "创建者已无权使用本执行组织"
            )

    @classmethod
    def authorize_request(cls, request, token: str) -> dict:
        claims = cls.decode_if_render(token)
        if claims is None:
            raise DashboardReportRenderScopeError("Render Session 无效")

        try:
            execution_id = int(claims["render_execution_id"])
            snapshot_id = int(claims["render_snapshot_id"])
            attempt_no = int(claims["render_attempt_no"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DashboardReportRenderScopeError("Render Session 缺少作用域") from exc

        try:
            execution = DashboardReportExecution.objects.select_related(
                "render_snapshot", "render_token", "snapshot"
            ).get(
                pk=execution_id,
                status=DashboardReportExecution.Status.RUNNING,
                creator=claims.get("creator_username", ""),
                creator_domain=claims.get("creator_domain", ""),
            )
            record: DashboardReportRenderToken = execution.render_token
        except (
            DashboardReportExecution.DoesNotExist,
            DashboardReportRenderToken.DoesNotExist,
        ) as exc:
            raise DashboardReportRenderScopeError("Render Session 已失效") from exc

        if (
            execution.render_snapshot.id != snapshot_id
            or record.attempt_no != attempt_no
            or record.consumed_at is None
            or record.revoked_at is not None
            or record.expires_at <= timezone.now()
        ):
            raise DashboardReportRenderScopeError("Render Session 已失效")

        if not SystemUser.objects.filter(
            username=execution.creator,
            domain=execution.creator_domain,
            disabled=False,
        ).exists():
            raise DashboardReportRenderScopeError("Render Session 已失效")

        execution_team_id = execution.snapshot.execution_team_id
        if not execution_team_id:
            raise DashboardReportRenderScopeError("Render Session 缺少组织作用域")
        # Render Worker 没有普通浏览器的 current_team cookie。通过与 API Key
        # 相同的可信请求属性把 Execution 创建时冻结的组织 identity 传给现有
        # DataSource 权限链；下游仍会实时校验创建者成员关系和 DataSource 权限。
        request._api_current_team = int(execution_team_id)
        cls.assert_creator_still_in_execution_team(
            creator_username=execution.creator,
            creator_domain=execution.creator_domain,
            execution_team_id=int(execution_team_id),
        )

        path = request.path
        method = request.method.upper()
        match = cls._RENDER_INPUT.match(path)
        if match and method == "GET" and int(match.group(1)) == execution_id:
            return claims

        allowed_datasources = {
            int(item["datasource_id"])
            for item in execution.render_snapshot.widget_manifest or []
            if item.get("datasource_id") is not None
        }
        match = cls._DATASOURCE_QUERY.match(path)
        if match and method == "POST" and int(match.group(1)) in allowed_datasources:
            return claims

        if cls._DATASOURCE_LIST.match(path) and method == "GET":
            raw_ids = request.GET.get("ids", "")
            try:
                requested_ids = {
                    int(item.strip()) for item in raw_ids.split(",") if item.strip()
                }
            except ValueError as exc:
                raise DashboardReportRenderScopeError("数据源作用域无效") from exc
            if requested_ids and requested_ids <= allowed_datasources:
                return claims

        if cls._NAMESPACE_LIST.match(path) and method == "GET":
            raw_ids = request.GET.get("ids", "")
            try:
                requested_ids = {
                    int(item.strip())
                    for item in raw_ids.split(",")
                    if item.strip()
                }
            except ValueError as exc:
                raise DashboardReportRenderScopeError(
                    "命名空间作用域无效"
                ) from exc
            allowed_namespace_ids = set(
                NameSpace.objects.filter(
                    data_sources__id__in=allowed_datasources
                ).values_list("id", flat=True)
            )
            if requested_ids and requested_ids <= allowed_namespace_ids:
                return claims

        if cls._NETWORK_STATUS_TOPOLOGY.match(path) and method == "POST":
            allowed_targets = cls._collect_network_status_topology_targets(
                execution.render_snapshot.view_sets
            )
            body = cls._read_json_body(request)
            model_id = body.get("model_id")
            inst_id = body.get("inst_id")
            if (
                model_id is not None
                and inst_id is not None
                and (str(model_id), str(inst_id)) in allowed_targets
            ):
                return claims

        raise DashboardReportRenderScopeError("Render Session 不允许访问该接口")

    @staticmethod
    def _read_json_body(request) -> dict:
        data = getattr(request, "data", None)
        if isinstance(data, dict):
            return data
        try:
            import json

            raw = getattr(request, "body", b"") or b""
            if not raw:
                return {}
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _collect_network_status_topology_targets(
        cls,
        view_sets,
    ) -> set[tuple[str, str]]:
        """从冻结 view_sets 收集允许的 (model_id, inst_id)。"""
        targets: set[tuple[str, str]] = set()

        def visit(item) -> None:
            if not isinstance(item, dict):
                return
            value_config = item.get("valueConfig") or {}
            scene_type = (
                value_config.get("sceneWidgetType")
                or item.get("sceneWidgetType")
                or value_config.get("chartType")
                or item.get("chartType")
            )
            config = (
                value_config.get("networkStatusTopology")
                or item.get("networkStatusTopology")
            )
            if scene_type == "networkStatusTopology" and isinstance(config, dict):
                model_id = config.get("modelId")
                inst_id = config.get("instId")
                if model_id is not None and inst_id is not None:
                    targets.add((str(model_id), str(inst_id)))
            children = (item.get("subGridOpts") or {}).get("children") or []
            for child in children:
                visit(child)

        if isinstance(view_sets, dict):
            for item in view_sets.get("items") or []:
                visit(item)
        elif isinstance(view_sets, list):
            for item in view_sets:
                visit(item)
        return targets
