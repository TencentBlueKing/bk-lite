"""Linux 批量安装命令：一条命令，每台用 --node_ip 受理。"""

from __future__ import annotations

import ipaddress
import shlex
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.logger import node_logger as logger
from apps.core.models.maintainer_info import maintainer_kwargs
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.models import CloudRegion, PackageVersion, SidecarEnv
from apps.node_mgmt.models.installer import ControllerBulkAttempt, ControllerBulkBatch
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from apps.node_mgmt.services.install_token import InstallTokenService
from apps.node_mgmt.services.module_push import ModulePushService, normalize_push_targets
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture

ACCEPTED_STATUSES = (
    InstallerConstants.BULK_ATTEMPT_INSTALLING,
    InstallerConstants.BULK_ATTEMPT_INSTALLED,
)
TERMINAL_BATCH_MESSAGES = {
    InstallerConstants.BULK_STATUS_REVOKED: "批量命令已撤销",
    InstallerConstants.BULK_STATUS_EXPIRED: "批量命令已过期",
    InstallerConstants.BULK_STATUS_DISABLED: "批量命令已停用",
}


@dataclass
class EnrollOutcome:
    accepted: bool
    message: str = ""
    install_token: str = ""
    node_id: str = ""


class BulkInstallService:
    @staticmethod
    def create_batch(
        *,
        cloud_region_id: int,
        package_id: int,
        max_success_count: int,
        expires_in_hours: int,
        push_targets: list[str],
        organization_id: int,
        username: str,
        domain: str,
        actor_scope: dict,
    ) -> dict:
        package = PackageVersion.objects.filter(id=package_id).first()
        if package is None or package.type != PackageConstants.TYPE_CONTROLLER or package.os != NodeConstants.LINUX_OS:
            raise ValidationAppException("没有匹配的控制器版本")
        if package.status != PackageVersion.STATUS_READY:
            raise ValidationAppException("没有匹配的控制器版本")
        if not CloudRegion.objects.filter(id=cloud_region_id).exists():
            raise ValidationAppException("云区域不存在")
        server_url = BulkInstallService._server_url(cloud_region_id)
        now = timezone.now()
        batch = ControllerBulkBatch.objects.create(
            token=str(uuid.uuid4()),
            cloud_region_id=cloud_region_id,
            organization_id=organization_id,
            package_version_id=package.id,
            max_success_count=max_success_count,
            expires_at=now + timedelta(hours=expires_in_hours),
            status=InstallerConstants.BULK_STATUS_ACTIVE,
            push_targets=normalize_push_targets(push_targets),
            actor_scope=actor_scope or {},
            **maintainer_kwargs(operator=username[:32], domain=domain),
        )
        logger.info(
            "bulk install batch created batch_id=%s max_success_count=%s",
            batch.id,
            batch.max_success_count,
        )
        return BulkInstallService._batch_payload(batch, server_url)

    @staticmethod
    def progress(*, batch: ControllerBulkBatch) -> dict:
        BulkInstallService._refresh_batch(batch)
        batch.refresh_from_db()
        return BulkInstallService._batch_payload(batch, BulkInstallService._server_url(batch.cloud_region_id))

    @staticmethod
    def revoke(*, batch: ControllerBulkBatch, username: str) -> dict:
        with transaction.atomic():
            locked = ControllerBulkBatch.objects.select_for_update().get(pk=batch.pk)
            if locked.status == InstallerConstants.BULK_STATUS_ACTIVE:
                locked.status = InstallerConstants.BULK_STATUS_REVOKED
                locked.revoked_by = (username or "")[:32]
                locked.save(update_fields=["status", "revoked_by", "updated_at"])
                logger.info("bulk install batch revoked batch_id=%s", locked.id)
            batch = locked
        return BulkInstallService._batch_payload(batch, BulkInstallService._server_url(batch.cloud_region_id))

    @staticmethod
    def render_bootstrap(token: str) -> str:
        batch = ControllerBulkBatch.objects.filter(token=token).first()
        if batch is None:
            raise ValidationAppException("批量命令不存在")
        server_url = BulkInstallService._server_url(batch.cloud_region_id).rstrip("/")
        return render_bulk_bootstrap_script(
            enroll_url=f"{server_url}/api/v1/node_mgmt/open_api/installer/bulk_enroll",
            result_url=f"{server_url}/api/v1/node_mgmt/open_api/installer/bulk_result",
            linux_bootstrap_url_prefix=f"{server_url}/api/v1/node_mgmt/open_api/installer/linux_bootstrap?token=",
            batch_token=batch.token,
        )

    @staticmethod
    def enroll(*, token: str, node_ip: str, hostname: str, cpu_architecture: str) -> EnrollOutcome:
        batch = ControllerBulkBatch.objects.filter(token=token).first()
        if batch is None:
            return EnrollOutcome(False, "批量命令不存在")
        normalized_ip = _parse_ipv4(node_ip)
        normalized_name = _normalize_hostname(hostname)
        normalized_arch = normalize_cpu_architecture(cpu_architecture)
        with transaction.atomic():
            locked_region = CloudRegion.objects.select_for_update().filter(id=batch.cloud_region_id).first()
            locked = ControllerBulkBatch.objects.select_for_update().get(pk=batch.pk)
            if locked_region is None:
                return BulkInstallService._reject(locked, "", "", "", "云区域不存在", count_failure=False)
            BulkInstallService._release_timed_out_attempts(locked)
            locked.refresh_from_db()
            terminal = BulkInstallService._terminal_message(locked)
            if terminal:
                return BulkInstallService._reject(locked, normalized_ip or "", normalized_name, normalized_arch, terminal, count_failure=False)
            if not normalized_ip:
                return BulkInstallService._reject(locked, str(node_ip or "")[:64], normalized_name, normalized_arch, "IP 地址不合法", count_failure=True)
            if not normalized_name:
                return BulkInstallService._reject(locked, normalized_ip, "", normalized_arch, "读不到主机名", count_failure=True)
            if not normalized_arch or not BulkInstallService._package_for_arch(locked.package_version_id, normalized_arch):
                return BulkInstallService._reject(
                    locked,
                    normalized_ip,
                    normalized_name,
                    normalized_arch,
                    "没有匹配的控制器版本",
                    count_failure=True,
                )
            existing = Node.objects.filter(cloud_region_id=locked.cloud_region_id, ip=normalized_ip).order_by("id").first()
            if existing is not None:
                message = f"IP {normalized_ip} 重复，节点 {existing.name}"
                return BulkInstallService._reject(
                    locked,
                    normalized_ip,
                    existing.name,
                    normalized_arch,
                    message,
                    status=InstallerConstants.BULK_ATTEMPT_DUPLICATE,
                    count_failure=False,
                )
            installing = (
                ControllerBulkAttempt.objects.select_for_update()
                .filter(
                    batch__cloud_region_id=locked.cloud_region_id,
                    ip=normalized_ip,
                    status=InstallerConstants.BULK_ATTEMPT_INSTALLING,
                )
                .order_by("id")
                .first()
            )
            if installing is not None:
                message = f"IP {normalized_ip} 重复，正在安装"
                if installing.node_name:
                    message = f"IP {normalized_ip} 重复，节点 {installing.node_name}"
                return BulkInstallService._reject(
                    locked,
                    normalized_ip,
                    installing.node_name,
                    normalized_arch,
                    message,
                    status=InstallerConstants.BULK_ATTEMPT_DUPLICATE,
                    count_failure=False,
                )
            accepted_count = ControllerBulkAttempt.objects.filter(batch=locked, status__in=ACCEPTED_STATUSES).count()
            if accepted_count >= locked.max_success_count:
                return BulkInstallService._reject(
                    locked,
                    normalized_ip,
                    normalized_name,
                    normalized_arch,
                    "成功台数已满",
                    count_failure=False,
                )
            node_id = str(uuid.uuid4())
            maintainer = maintainer_kwargs(operator=locked.created_by, domain=locked.domain)
            node = Node.objects.create(
                id=node_id,
                name=normalized_name,
                ip=normalized_ip,
                operating_system=NodeConstants.LINUX_OS,
                cpu_architecture=normalized_arch,
                collector_configuration_directory=InstallerConstants.LINUX_INSTALL_DEFAULT_DIR,
                cloud_region_id=locked.cloud_region_id,
                install_method=ControllerConstants.MANUAL,
                **maintainer,
            )
            NodeOrganization.objects.create(node=node, organization=locked.organization_id, **maintainer)
            ControllerBulkAttempt.objects.create(
                batch=locked,
                ip=normalized_ip,
                node_name=normalized_name,
                cpu_architecture=normalized_arch,
                node_id=node_id,
                status=InstallerConstants.BULK_ATTEMPT_INSTALLING,
                message="",
            )
            install_token = InstallTokenService.generate_install_token(
                node_id=node_id,
                ip=normalized_ip,
                user=locked.created_by or "bulk",
                os=NodeConstants.LINUX_OS,
                package_id=locked.package_version_id,
                cloud_region_id=locked.cloud_region_id,
                organizations=[locked.organization_id],
                node_name=normalized_name,
                cpu_architecture=normalized_arch,
                install_mode="manual",
            )
            targets = normalize_push_targets(locked.push_targets)
            actor_scope = locked.actor_scope if isinstance(locked.actor_scope, dict) else {}
        if targets:
            ModulePushService.remember_deferred_push(
                cloud_region_id=batch.cloud_region_id,
                nodes=[{"ip": normalized_ip, "node_id": node_id}],
                targets=targets,
                actor_scope=actor_scope,
            )
        logger.debug("bulk install enroll batch_id=%s outcome=installing", batch.id)
        return EnrollOutcome(True, install_token=install_token, node_id=node_id)

    @staticmethod
    def report(*, token: str, node_id: str, outcome: str) -> EnrollOutcome:
        batch = ControllerBulkBatch.objects.filter(token=token).first()
        if batch is None:
            return EnrollOutcome(False, "批量命令不存在")
        if outcome not in {"success", "failed"}:
            return EnrollOutcome(False, "安装结果不合法")
        with transaction.atomic():
            CloudRegion.objects.select_for_update().filter(id=batch.cloud_region_id).first()
            locked = ControllerBulkBatch.objects.select_for_update().get(pk=batch.pk)
            attempt = (
                ControllerBulkAttempt.objects.select_for_update()
                .filter(batch=locked, node_id=node_id, status=InstallerConstants.BULK_ATTEMPT_INSTALLING)
                .first()
            )
            if attempt is None:
                return EnrollOutcome(False, "安装状态已结束")
            if outcome == "success":
                attempt.status = InstallerConstants.BULK_ATTEMPT_INSTALLED
                attempt.message = ""
                attempt.save(update_fields=["status", "message", "updated_at"])
                logger.debug("bulk install enroll batch_id=%s outcome=installed", locked.id)
                return EnrollOutcome(True, node_id=node_id)
            BulkInstallService._delete_placeholder_node(attempt.node_id)
            attempt.status = InstallerConstants.BULK_ATTEMPT_FAILED
            attempt.message = "安装失败"
            attempt.counts_toward_disable = True
            attempt.save(update_fields=["status", "message", "counts_toward_disable", "updated_at"])
            BulkInstallService._disable_if_needed(locked)
            logger.debug("bulk install enroll batch_id=%s outcome=failed", locked.id)
            return EnrollOutcome(True, message="安装失败", node_id=node_id)

    @staticmethod
    def _reject(
        batch: ControllerBulkBatch,
        ip: str,
        node_name: str,
        cpu_architecture: str,
        message: str,
        *,
        status: str = InstallerConstants.BULK_ATTEMPT_FAILED,
        count_failure: bool,
    ) -> EnrollOutcome:
        ControllerBulkAttempt.objects.create(
            batch=batch,
            ip=(ip or "")[:64],
            node_name=(node_name or "")[:100],
            cpu_architecture=(cpu_architecture or "")[:20],
            status=status,
            message=message[:500],
            counts_toward_disable=count_failure,
        )
        if count_failure:
            BulkInstallService._disable_if_needed(batch)
        logger.debug("bulk install enroll batch_id=%s outcome=%s", batch.id, status)
        return EnrollOutcome(False, message)

    @staticmethod
    def _disable_if_needed(batch: ControllerBulkBatch) -> None:
        if batch.status != InstallerConstants.BULK_STATUS_ACTIVE:
            return
        failure_count = ControllerBulkAttempt.objects.filter(batch=batch, counts_toward_disable=True).count()
        if failure_count >= batch.max_success_count * InstallerConstants.BULK_FAILURE_MULTIPLIER:
            batch.status = InstallerConstants.BULK_STATUS_DISABLED
            batch.save(update_fields=["status", "updated_at"])
            logger.info("bulk install batch disabled batch_id=%s", batch.id)

    @staticmethod
    def _terminal_message(batch: ControllerBulkBatch) -> str:
        if batch.status == InstallerConstants.BULK_STATUS_ACTIVE and timezone.now() >= batch.expires_at:
            batch.status = InstallerConstants.BULK_STATUS_EXPIRED
            batch.save(update_fields=["status", "updated_at"])
        if batch.status == InstallerConstants.BULK_STATUS_ACTIVE:
            failure_count = ControllerBulkAttempt.objects.filter(batch=batch, counts_toward_disable=True).count()
            if failure_count >= batch.max_success_count * InstallerConstants.BULK_FAILURE_MULTIPLIER:
                batch.status = InstallerConstants.BULK_STATUS_DISABLED
                batch.save(update_fields=["status", "updated_at"])
        return TERMINAL_BATCH_MESSAGES.get(batch.status, "")

    @staticmethod
    def _release_timed_out_attempts(batch: ControllerBulkBatch) -> None:
        deadline = timezone.now() - timedelta(seconds=InstallerConstants.BULK_INSTALL_TIMEOUT_SECONDS)
        timed_out_ids = list(
            ControllerBulkAttempt.objects.filter(
                batch__cloud_region_id=batch.cloud_region_id,
                status=InstallerConstants.BULK_ATTEMPT_INSTALLING,
                created_at__lt=deadline,
            )
            .order_by("id")
            .values_list("id", flat=True)[: InstallerConstants.BULK_TIMEOUT_RELEASE_LIMIT]
        )
        timed_out = ControllerBulkAttempt.objects.select_for_update().filter(id__in=timed_out_ids).order_by("id")
        for attempt in timed_out:
            if BulkInstallService._placeholder_has_reported(attempt.node_id):
                attempt.status = InstallerConstants.BULK_ATTEMPT_INSTALLED
                attempt.message = ""
                attempt.save(update_fields=["status", "message", "updated_at"])
                continue
            BulkInstallService._delete_placeholder_node(attempt.node_id)
            attempt.status = InstallerConstants.BULK_ATTEMPT_TIMEOUT
            attempt.message = "安装超时"
            attempt.save(update_fields=["status", "message", "updated_at"])

    @staticmethod
    def _placeholder_has_reported(node_id: str) -> bool:
        if not node_id:
            return False
        node = Node.objects.select_for_update().filter(id=node_id).first()
        return node is not None and bool(node.status)

    @staticmethod
    def _delete_placeholder_node(node_id: str) -> None:
        if not node_id:
            return
        Node.objects.filter(id=node_id).delete()

    @staticmethod
    def _package_for_arch(package_id: int, cpu_architecture: str):
        resolved = PackageService.resolve_package_by_architecture(package_id, cpu_architecture)
        if resolved is None or resolved.os != NodeConstants.LINUX_OS or resolved.status != PackageVersion.STATUS_READY:
            return None
        if resolved.type != PackageConstants.TYPE_CONTROLLER:
            return None
        return resolved

    @staticmethod
    def _refresh_batch(batch: ControllerBulkBatch) -> None:
        with transaction.atomic():
            locked = ControllerBulkBatch.objects.select_for_update().get(pk=batch.pk)
            BulkInstallService._release_timed_out_attempts(locked)
            BulkInstallService._terminal_message(locked)

    @staticmethod
    def _server_url(cloud_region_id: int) -> str:
        env = SidecarEnv.objects.filter(cloud_region_id=cloud_region_id, key=NodeConstants.SERVER_URL_KEY).first()
        value = (env.value if env else "").strip()
        if not value:
            raise ValidationAppException("缺少节点服务地址")
        return value

    @staticmethod
    def _batch_payload(batch: ControllerBulkBatch, server_url: str) -> dict:
        accepted_count = ControllerBulkAttempt.objects.filter(batch=batch, status__in=ACCEPTED_STATUSES).count()
        failure_count = ControllerBulkAttempt.objects.filter(batch=batch, counts_toward_disable=True).count()
        attempts = list(batch.attempts.order_by("-id")[: InstallerConstants.BULK_PROGRESS_ITEM_LIMIT])
        attempts.reverse()
        return {
            "batch_id": batch.id,
            "status": batch.status,
            "max_success_count": batch.max_success_count,
            "accepted_count": accepted_count,
            "failure_count": failure_count,
            "expires_at": batch.expires_at.isoformat(),
            "command": build_bulk_command(server_url, batch.token),
            "items": [
                {
                    "ip": item.ip,
                    "node_name": item.node_name,
                    "cpu_architecture": item.cpu_architecture,
                    "status": item.status,
                    "message": item.message,
                }
                for item in attempts
            ],
        }


def build_bulk_command(server_url: str, token: str) -> str:
    bootstrap_url = f"{server_url.rstrip('/')}/api/v1/node_mgmt/open_api/installer/bulk_bootstrap?token={token}"
    return f"curl -fsSLk {shlex.quote(bootstrap_url)} | sudo bash -s -- --node_ip <主机IP>"


def render_bulk_bootstrap_script(*, enroll_url: str, result_url: str, linux_bootstrap_url_prefix: str, batch_token: str) -> str:
    token = shlex.quote(batch_token)
    enroll = shlex.quote(enroll_url)
    result = shlex.quote(result_url)
    prefix = shlex.quote(linux_bootstrap_url_prefix)
    return f"""#!/bin/sh
set -eu
BATCH_TOKEN={token}
ENROLL_URL={enroll}
RESULT_URL={result}
BOOTSTRAP_PREFIX={prefix}
NODE_IP=""
REPORTED=0
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--node_ip" ]; then
    if [ "$#" -lt 2 ]; then
      echo "IP 地址不合法" >&2
      exit 1
    fi
    NODE_IP="$2"
    shift 2
  else
    echo "Error: unsupported argument $1" >&2
    exit 1
  fi
done
if [ -z "$NODE_IP" ]; then
  echo "--node_ip is required" >&2
  exit 1
fi
printf '%s\\n' "$NODE_IP" | grep -Eq '^([0-9]{{1,3}}\\.){{3}}[0-9]{{1,3}}$' || {{
  echo "IP 地址不合法" >&2
  exit 1
}}
found=0
if command -v ip >/dev/null 2>&1; then
  for addr in $(ip -4 -o addr show | awk '{{print $4}}' | cut -d/ -f1); do
    if [ "$addr" = "$NODE_IP" ]; then
      found=1
    fi
  done
fi
if [ "$found" -ne 1 ] && command -v ifconfig >/dev/null 2>&1; then
  for addr in $(ifconfig | awk '/inet / {{ gsub(/addr:/, "", $2); print $2 }}'); do
    if [ "$addr" = "$NODE_IP" ]; then
      found=1
    fi
  done
fi
if [ "$found" -ne 1 ]; then
  echo "本机网卡上没有这个地址" >&2
  exit 1
fi
NODE_NAME=$(hostname 2>/dev/null || true)
NODE_NAME=$(printf '%s' "$NODE_NAME" | tr -d '\\r\\n')
if [ -z "$NODE_NAME" ]; then
  echo "读不到主机名" >&2
  exit 1
fi
DETECTED_ARCH=$(uname -m | tr '[:upper:]' '[:lower:]')
if [ "$DETECTED_ARCH" = "amd64" ]; then
  DETECTED_ARCH="x86_64"
elif [ "$DETECTED_ARCH" = "aarch64" ]; then
  DETECTED_ARCH="arm64"
fi
BODY=$(mktemp)
BOOTSTRAP_FILE=""
cleanup() {{
  rm -f "$BODY"
  if [ -n "$BOOTSTRAP_FILE" ]; then
    rm -f "$BOOTSTRAP_FILE"
  fi
}}
report_outcome() {{
  if [ "$REPORTED" -eq 1 ]; then
    return 0
  fi
  REPORTED=1
  _outcome="$1"
  for _try in 1 2 3 4; do
    if curl -sSLk -o /dev/null -X POST "$RESULT_URL" \
      --data-urlencode "token=$BATCH_TOKEN" \
      --data-urlencode "node_id=$NODE_ID" \
      --data-urlencode "outcome=$_outcome"; then
      return 0
    fi
    if [ "$_try" -lt 4 ]; then
      sleep 2
    fi
  done
  return 0
}}
on_interrupt() {{
  report_outcome failed
  exit 130
}}
trap cleanup 0
CODE=$(curl -sSLk -o "$BODY" -w '%{{http_code}}' -X POST "$ENROLL_URL" \
  --data-urlencode "token=$BATCH_TOKEN" \
  --data-urlencode "node_ip=$NODE_IP" \
  --data-urlencode "hostname=$NODE_NAME" \
  --data-urlencode "cpu_architecture=$DETECTED_ARCH")
if [ "$CODE" != "200" ]; then
  cat "$BODY" >&2
  exit 1
fi
INSTALL_TOKEN=$(sed -n '1p' "$BODY")
NODE_ID=$(sed -n '2p' "$BODY")
if [ -z "$INSTALL_TOKEN" ] || [ -z "$NODE_ID" ]; then
  echo "安装受理失败" >&2
  exit 1
fi
trap 'on_interrupt' HUP INT TERM
BOOTSTRAP_FILE=$(mktemp)
installer_status=0
curl -fsSLk "$BOOTSTRAP_PREFIX$INSTALL_TOKEN" -o "$BOOTSTRAP_FILE" || installer_status=$?
if [ "$installer_status" -eq 0 ]; then
  sh "$BOOTSTRAP_FILE" || installer_status=$?
fi
OUTCOME=failed
if [ "$installer_status" -eq 0 ]; then
  OUTCOME=success
fi
report_outcome "$OUTCOME"
exit "$installer_status"
"""


def _parse_ipv4(value: str) -> str:
    try:
        parsed = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return ""
    if parsed.version != 4:
        return ""
    return str(parsed)


def _normalize_hostname(value: str) -> str:
    hostname = str(value or "").replace("\r", "").replace("\n", "").strip()
    return hostname[:100]
