"""环境安装的范围校验、额度和幂等契约。"""
import hmac
import ipaddress
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.node_mgmt.models import CloudRegion, EnvironmentInstallAttempt, EnvironmentInstallGrant, Node, NodeOrganization, PackageVersion
from apps.system_mgmt.models import SystemAPIToken

INSTALL_ENDPOINTS = ["POST node-mgmt/environment-install", "POST node-mgmt/environment-install-status"]
HEARTBEAT_FRESHNESS = timedelta(minutes=2)


def heartbeat_is_fresh(last_heartbeat_at, created_at, *, now=None):
    """心跳必须不早于建档时间，并且落在最近两分钟内。"""
    if last_heartbeat_at is None or created_at is None:
        return False
    current = now or timezone.now()
    return last_heartbeat_at >= max(created_at, current - HEARTBEAT_FRESHNESS)


class EnvironmentInstallService:
    @staticmethod
    @transaction.atomic
    def create(*, owner, domain, team, cloud_region_id, package_id, expires_at, max_nodes, required_collectors=None):
        if not owner or not domain or team < 1 or not 1 <= max_nodes <= 10000:
            raise ValueError("invalid installation scope")
        if expires_at <= timezone.now():
            raise ValueError("expired installation grant")
        package = PackageVersion.objects.select_for_update().get(pk=package_id)
        if (
            package.type != "controller"
            or package.version == "latest"
            or package.os != "linux"
            or package.cpu_architecture != "x86_64"
            or package.status != PackageVersion.STATUS_READY
        ):
            raise ValueError("unsupported package")
        if len(package.sha256) != 64 or any(c not in "0123456789abcdef" for c in package.sha256):
            raise ValueError("package digest required")
        region = CloudRegion.objects.get(pk=cloud_region_id)
        selected = list(dict.fromkeys(required_collectors or []))
        options = {item["id"]: item for item in EnvironmentInstallService.component_options(region.pk)}
        if len(selected) > 20 or any(item not in options for item in selected):
            raise ValueError("unsupported required collector")
        grant = EnvironmentInstallGrant(
            owner=owner,
            domain=domain,
            team=team,
            cloud_region=region,
            package=package,
            package_sha256=package.sha256,
            package_version=package.version,
            max_nodes=max_nodes,
            required_components=[options[item] for item in selected],
        )
        key = SystemAPIToken.generate_secret()
        # The token column is shorter than a username. Authorization uses grant.owner.
        created_by_limit = SystemAPIToken._meta.get_field("created_by").max_length
        grant.token = SystemAPIToken.objects.create(
            system_id="node-environment-install",
            name=str(grant.id),
            secret_hash=SystemAPIToken.hash_secret(key),
            scope={"mode": "allowlist", "endpoints": INSTALL_ENDPOINTS},
            expires_at=expires_at,
            created_by=owner[:created_by_limit],
            created_by_domain=domain,
        )
        grant.save()
        return grant, key

    @staticmethod
    def component_options(cloud_region_id):
        from apps.node_mgmt.constants.collector import CollectorConstants
        from apps.node_mgmt.models import Collector, SidecarEnv

        mode = SidecarEnv.objects.filter(cloud_region_id=cloud_region_id, key="SIDECAR_INPUT_MODE").values_list("value", flat=True).first() or "nats"
        candidates = (
            Collector.objects.filter(node_operating_system="linux", cpu_architecture__in=["x86_64", ""], controller_default_run=True)
            .exclude(name__in=CollectorConstants.DEFAULT_CONTAINER_COLLECTOR_CONFIGS)
            .order_by("name", "-cpu_architecture", "id")
        )
        preferred = {}
        for item in candidates:
            preferred.setdefault(item.name, item)
        return [
            {"id": item.id, "name": item.name}
            for item in preferred.values()
            if isinstance(item.default_config, dict) and item.default_config.get(mode)
        ]

    @staticmethod
    def _authorize(grant_id, installation_key, team, user_info):
        region_id = EnvironmentInstallGrant.objects.values_list("cloud_region_id", flat=True).get(pk=grant_id)
        # Keep the same region -> grant lock order as the first heartbeat path.
        CloudRegion.objects.select_for_update().get(pk=region_id)
        grant = EnvironmentInstallGrant.objects.select_for_update().get(pk=grant_id)
        token = SystemAPIToken.objects.select_for_update().get(pk=grant.token_id)
        if (
            not token.is_live()
            or not installation_key.startswith(SystemAPIToken.PREFIX)
            or not hmac.compare_digest(token.secret_hash, SystemAPIToken.hash_secret(installation_key))
            or set(team or []) != {grant.team}
            or (user_info or {}).get("user") != grant.owner
            or (user_info or {}).get("domain") != grant.domain
        ):
            raise PermissionError("installation grant denied")
        package = PackageVersion.objects.select_for_update().get(pk=grant.package_id)
        if package.status != PackageVersion.STATUS_READY or package.sha256 != grant.package_sha256 or package.version != grant.package_version:
            raise ValueError("package changed")
        return grant

    @staticmethod
    def _result(attempt):
        return {
            "install_id": str(attempt.id),
            "node_id": attempt.node_id,
            "status": "registered" if attempt.registered_at else "pending",
        }

    @staticmethod
    @transaction.atomic
    def reserve(*, grant_id, installation_key, request_id, node_id, ip, node_name, os, cpu_architecture, team, user_info):
        grant = EnvironmentInstallService._authorize(grant_id, installation_key, team, user_info)
        request_id = UUID(str(request_id))
        node_id = str(UUID(str(node_id)))
        ip = str(ipaddress.IPv4Address(ip))
        if os != "linux" or cpu_architecture != "x86_64" or len(node_name) > 100 or any(c in node_name for c in "\r\n"):
            raise ValueError("unsupported node")
        existing = grant.attempts.filter(request_id=request_id).first()
        if existing:
            if (existing.node_id, existing.ip, existing.node_name) != (node_id, ip, node_name):
                raise ValueError("request conflict")
            return EnvironmentInstallService._result(existing)
        if grant.attempts.count() >= grant.max_nodes:
            raise ValueError("installation quota exceeded")
        if Node.objects.filter(pk=node_id).exists() or EnvironmentInstallAttempt.objects.filter(node_id=node_id).exists():
            raise ValueError("node identity conflict")
        if (
            Node.objects.filter(cloud_region_id=grant.cloud_region_id, ip=ip).exists()
            or EnvironmentInstallAttempt.objects.filter(grant__cloud_region_id=grant.cloud_region_id, ip=ip).exists()
        ):
            raise ValueError("node address conflict")
        attempt = EnvironmentInstallAttempt.objects.create(grant=grant, request_id=request_id, node_id=node_id, ip=ip, node_name=node_name)
        return EnvironmentInstallService._result(attempt)

    @staticmethod
    def status(*, grant_id, installation_key, install_id, team, user_info, report=None):
        from nats.errors import Error as NatsError

        from apps.rpc.exceptions import RpcTimeoutError
        from apps.rpc.executor import Executor

        result = EnvironmentInstallService._status_snapshot(
            grant_id=grant_id,
            installation_key=installation_key,
            install_id=install_id,
            team=team,
            user_info=user_info,
            report=report,
        )
        executor = next((item for item in result["components"] if item["name"] == "NATS-Executor"), None)
        if executor is None:
            return result  # Existing grants keep their original signed contract.
        ready = False
        # External RPC must not hold region/grant/attempt database locks.
        if result["status"] == "registered" and executor["status"] == "healthy":
            try:
                health = Executor(result["node_id"]).health_check(timeout=3)
                ready = isinstance(health, dict) and health.get("success") is True and health.get("instance_id") == result["node_id"]
            except (NatsError, RpcTimeoutError, TimeoutError, OSError):
                ready = False
        result["executor_rpc_ready"] = ready
        if not ready:
            executor["status"] = "unhealthy"
            result["components_healthy"] = False
        return result

    @staticmethod
    @transaction.atomic
    def _status_snapshot(*, grant_id, installation_key, install_id, team, user_info, report=None):
        grant = EnvironmentInstallService._authorize(grant_id, installation_key, team, user_info)
        attempt = grant.attempts.select_for_update().get(pk=install_id)
        if report is not None:
            if report.get("stage") not in {
                "request",
                "identity",
                "session",
                "preflight",
                "download",
                "extract",
                "install",
                "registration",
                "components",
                "result",
                "complete",
            } or report.get("error_code") not in {0, 10, 20, 30, 40, 50, 60, 70}:
                raise ValueError("invalid installation report")
            attempt.failure_stage = report["stage"] if report["error_code"] else ""
            attempt.error_code = report["error_code"]
            attempt.last_reported_at = timezone.now()
            attempt.save(update_fields=["failure_stage", "error_code", "last_reported_at"])
        result = EnvironmentInstallService._result(attempt)
        node = Node.objects.filter(pk=attempt.node_id, cloud_region_id=grant.cloud_region_id, ip=attempt.ip).first()
        if (
            not node
            or not attempt.registered_at
            or not heartbeat_is_fresh(attempt.last_heartbeat_at, attempt.created_at)
            or f"environment_install:{attempt.id}" not in node.tags
            or f"environment_package_sha256:{grant.package_sha256}" not in node.tags
            or set(NodeOrganization.objects.filter(node_id=attempt.node_id).values_list("organization", flat=True)) != {grant.team}
        ):
            result["status"] = "pending"
        result["last_seen"] = attempt.last_heartbeat_at.isoformat() if attempt.last_heartbeat_at else None
        result["package_version"] = grant.package_version
        reported = (node.status or {}).get("collectors", []) if node and isinstance(node.status, dict) else []
        if not isinstance(reported, list):
            reported = []
        components = []
        for required in grant.required_components:
            matches = [item for item in reported if isinstance(item, dict) and item.get("collector_id") == required["id"]]
            healthy = result["status"] == "registered" and len(matches) == 1 and type(matches[0].get("status")) is int and matches[0]["status"] == 0
            components.append({**required, "status": "healthy" if healthy else "unhealthy"})
        result.update(components=components, components_healthy=all(item["status"] == "healthy" for item in components))
        result.update(failure_stage=attempt.failure_stage, error_code=attempt.error_code)
        return result

    @staticmethod
    def describe_attempts(grant, rows):
        """Attach heartbeat component health and executor RPC readiness to one result page."""
        node_ids = [row["node_id"] for row in rows]
        nodes = {node.id: node for node in Node.objects.filter(pk__in=node_ids, cloud_region_id=grant.cloud_region_id)}
        described = []
        rpc_targets = []
        for row in rows:
            item = dict(row)
            registered = bool(row.get("registered_at"))
            fresh = heartbeat_is_fresh(row.get("last_heartbeat_at"), row.get("created_at"))
            components = EnvironmentInstallService._component_rows(grant, nodes.get(row["node_id"]), registered and fresh)
            item["components"] = components
            item["components_healthy"] = all(component["status"] == "healthy" for component in components)
            executor = next((component for component in components if component.get("name") == "NATS-Executor"), None)
            if executor is None:
                item["executor_rpc_ready"] = None
            elif executor["status"] != "healthy":
                item["executor_rpc_ready"] = False
            else:
                item["executor_rpc_ready"] = False
                rpc_targets.append(item)
            described.append(item)
        EnvironmentInstallService._fill_executor_rpc(rpc_targets)
        return described

    @staticmethod
    def _component_rows(grant, node, registered):
        reported = (node.status or {}).get("collectors", []) if node and isinstance(getattr(node, "status", None), dict) else []
        if not isinstance(reported, list):
            reported = []
        components = []
        for required in grant.required_components or []:
            if not isinstance(required, dict):
                continue
            matches = [item for item in reported if isinstance(item, dict) and item.get("collector_id") == required.get("id")]
            healthy = registered and len(matches) == 1 and type(matches[0].get("status")) is int and matches[0]["status"] == 0
            components.append({**required, "status": "healthy" if healthy else "unhealthy"})
        return components

    @staticmethod
    def _fill_executor_rpc(items):
        if not items:
            return
        from concurrent.futures import ThreadPoolExecutor

        from nats.errors import Error as NatsError

        from apps.rpc.exceptions import RpcTimeoutError
        from apps.rpc.executor import Executor

        def probe(node_id):
            try:
                health = Executor(node_id).health_check(timeout=3)
            except (NatsError, RpcTimeoutError, TimeoutError, OSError):
                return False
            return isinstance(health, dict) and health.get("success") is True and health.get("instance_id") == node_id

        with ThreadPoolExecutor(max_workers=min(4, len(items))) as pool:
            futures = {pool.submit(probe, item["node_id"]): item for item in items}
            for future, item in futures.items():
                try:
                    ready = future.result()
                except Exception:
                    ready = False
                item["executor_rpc_ready"] = ready
                if ready:
                    continue
                for component in item["components"]:
                    if component.get("name") == "NATS-Executor":
                        component["status"] = "unhealthy"
                item["components_healthy"] = all(component["status"] == "healthy" for component in item["components"])

    @staticmethod
    @transaction.atomic
    def validate_registration(node_id, details):
        """Only new environment-managed identities are constrained; legacy stays unchanged."""
        attempt = EnvironmentInstallAttempt.objects.filter(node_id=node_id).first()
        if attempt is None:
            return None
        grant = EnvironmentInstallGrant.objects.select_for_update().get(pk=attempt.grant_id)
        token = SystemAPIToken.objects.select_for_update().get(pk=grant.token_id)
        attempt = EnvironmentInstallAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.registered_at:
            raise PermissionError("installation identity already registered; explicit recovery required")
        if not token.is_live():
            raise PermissionError("installation grant revoked or expired")
        from apps.node_mgmt.utils.sidecar import format_tags_dynamic

        tags = format_tags_dynamic(details.get("tags", []), ["zone", "group"])
        if tags.get("zone") != [str(grant.cloud_region_id)] or tags.get("group") != [str(grant.team)]:
            raise PermissionError("installation registration scope mismatch")
        if details.get("ip") != attempt.ip:
            raise PermissionError("installation registration address mismatch")
        required_tags = {f"environment_install:{attempt.id}", f"environment_package_sha256:{grant.package_sha256}"}
        if not required_tags.issubset(set(details.get("tags", []))):
            raise PermissionError("installation receipt mismatch")
        return attempt

    @staticmethod
    @transaction.atomic
    def request(**kwargs):
        from urllib.parse import urlsplit

        from apps.node_mgmt.models import SidecarEnv
        from apps.node_mgmt.services.install_token import InstallTokenService

        result = EnvironmentInstallService.reserve(**kwargs)
        grant = EnvironmentInstallService._authorize(kwargs["grant_id"], kwargs["installation_key"], kwargs["team"], kwargs["user_info"])
        result.update(package_sha256=grant.package_sha256, package_version=grant.package_version)
        if result["status"] == "registered":
            if not Node.objects.filter(pk=result["node_id"], cloud_region_id=grant.cloud_region_id, ip=kwargs["ip"]).exists():
                raise ValueError("registered node identity conflict")
            return result
        server_url = SidecarEnv.objects.get(cloud_region_id=grant.cloud_region_id, key="NODE_SERVER_URL").value.rstrip("/")
        parsed = urlsplit(server_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("HTTPS platform URL required")
        token = InstallTokenService.generate_install_token(
            node_id=result["node_id"],
            ip=kwargs["ip"],
            user=grant.owner,
            os="linux",
            package_id=grant.package_id,
            cloud_region_id=grant.cloud_region_id,
            organizations=[grant.team],
            node_name=kwargs["node_name"],
            cpu_architecture="x86_64",
            environment_grant_id=str(grant.id),
        )
        result.update(
            config_url=f"{server_url}/api/v1/node_mgmt/open_api/installer/session?token={token}",
            package_sha256=grant.package_sha256,
            package_version=grant.package_version,
        )
        return result

    @staticmethod
    @transaction.atomic
    def validate_session(token_data):
        from apps.core.exceptions.base_app_exception import UnauthorizedException

        attempt = EnvironmentInstallAttempt.objects.filter(node_id=token_data["node_id"]).first()
        grant_id = token_data.get("environment_grant_id")
        if not attempt and not grant_id:
            return False
        if not attempt or str(attempt.grant_id) != grant_id:
            raise UnauthorizedException("environment installation session mismatch")
        grant = EnvironmentInstallGrant.objects.select_for_update().get(pk=attempt.grant_id)
        token = SystemAPIToken.objects.select_for_update().get(pk=grant.token_id)
        attempt.refresh_from_db()
        if attempt.registered_at:
            raise UnauthorizedException("environment installation already registered")
        package = PackageVersion.objects.select_for_update().get(pk=grant.package_id)
        if package.sha256 != grant.package_sha256 or package.version != grant.package_version or package.status != PackageVersion.STATUS_READY:
            raise UnauthorizedException("environment installation package changed")
        if not token.is_live():
            raise UnauthorizedException("environment installation grant expired or revoked")
        expected = {
            "ip": attempt.ip,
            "user": grant.owner,
            "organizations": [grant.team],
            "cloud_region_id": grant.cloud_region_id,
            "package_id": grant.package_id,
            "os": "linux",
            "cpu_architecture": "x86_64",
        }
        if any(token_data.get(key) != value for key, value in expected.items()):
            raise UnauthorizedException("environment installation session scope mismatch")
        return True

    @staticmethod
    def record_heartbeat(node_id, details):
        attempt = EnvironmentInstallAttempt.objects.select_related("grant").filter(node_id=node_id, registered_at__isnull=False).first()
        if attempt is None:
            return
        tags = set(details.get("tags", []))
        expected = {f"environment_install:{attempt.id}", f"environment_package_sha256:{attempt.grant.package_sha256}"}
        if details.get("ip") == attempt.ip and expected.issubset(tags):
            EnvironmentInstallAttempt.objects.filter(pk=attempt.pk).update(last_heartbeat_at=timezone.now())
