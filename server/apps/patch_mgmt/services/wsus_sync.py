"""WSUS PowerShell 客户端 + 补丁同步服务。

通过 WinRM 远程执行 PowerShell，调用 Microsoft.UpdateServices.Administration
管理 API 获取补丁元数据。

同步流程:
  1. WsusClient.check_connection() -> AdminProxy.GetUpdateServer() 连通性检测
  2. WsusClient.get_approved_updates() -> GetUpdates(ApprovedStates) 补丁列表
  3. 每条补丁 -> Patch + WindowsPatchDetail（元数据入库）

认证: WinRM NTLM。
依赖: pywinrm + requests_ntlm。
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

import winrm
from django.utils import timezone

from apps.patch_mgmt.models import PatchSource

logger = logging.getLogger("app")

WINRM_PORT = 5985
DEFAULT_WSUS_PORT = 8530
MAX_UPDATES = 200


class WsusSyncError(Exception):
    """WSUS 同步异常。"""


@dataclass
class WsusUpdate:
    """WSUS 补丁条目。"""

    update_id: str
    title: str
    kb_number: str = ""
    classification: str = ""
    severity: str = ""
    products: List[str] = field(default_factory=list)
    security_bulletins: List[str] = field(default_factory=list)
    description: str = ""
    arrival_date: str = ""


class WsusClient:
    """WSUS PowerShell 客户端。

    通过 WinRM 远程执行 PowerShell，调用 Microsoft.UpdateServices.Administration
    管理 API 获取补丁元数据。不依赖 SOAP API。
    """

    def __init__(self, source: PatchSource):
        self.source = source
        self.host, self.wsus_port = self._parse_url(source)
        self.winrm_url = f"http://{self.host}:{WINRM_PORT}/wsman"
        self.auth_user = source.auth_user or ""
        self.auth_password = source.get_auth_password()

    @staticmethod
    def _parse_url(source: PatchSource) -> tuple[str, int]:
        url = (source.url or "").strip()
        if not url:
            raise WsusSyncError("WSUS 源未配置 URL")
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            raise WsusSyncError(f"WSUS 源 URL 格式无效: {source.url}")
        port = parsed.port or DEFAULT_WSUS_PORT
        return host, port

    def _run_ps(self, script: str) -> str:
        """通过 WinRM 执行 PowerShell 脚本，返回 stdout。"""
        try:
            session = winrm.Session(
                self.winrm_url,
                auth=(self.auth_user, self.auth_password),
                transport="ntlm",
            )
            result = session.run_ps(script)
        except Exception as exc:
            raise WsusSyncError(f"WinRM 连接失败 ({self.host}): {exc}")

        if result.status_code != 0:
            stderr = result.std_err.decode("utf-8", errors="replace")
            raise WsusSyncError(f"PowerShell 执行失败: {stderr[:500]}")

        return result.std_out.decode("utf-8", errors="replace")

    def check_connection(self) -> bool:
        """通过 PowerShell AdminProxy.GetUpdateServer() 检测连通性。

        Returns:
            True 如果服务器可达且 AdminProxy 能连接。
        """
        script = (
            '[reflection.assembly]::LoadWithPartialName("Microsoft.UpdateServices.Administration") | Out-Null;'
            "try {"
            f'$wsus = [Microsoft.UpdateServices.Administration.AdminProxy]::GetUpdateServer("localhost", $false, {self.wsus_port});'
            'Write-Output "OK"'
            "} catch {"
            'Write-Output "ERROR: $_"'
            "}"
        )
        try:
            output = self._run_ps(script)
            return "OK" in output
        except WsusSyncError as exc:
            logger.warning("WsusClient.check_connection 失败: %s", exc)
            return False

    def get_approved_updates(self) -> List[WsusUpdate]:
        """获取 WSUS 服务器上已批准的补丁列表。

        Returns:
            WsusUpdate 列表（最多 MAX_UPDATES 条）。
        """
        script = self._build_get_updates_script()
        output = self._run_ps(script)
        return self._parse_updates_json(output)

    def _build_get_updates_script(self) -> str:
        """构建获取已批准补丁列表的 PowerShell 脚本。"""
        return (
            '[reflection.assembly]::LoadWithPartialName("Microsoft.UpdateServices.Administration") | Out-Null;'
            f'$wsus = [Microsoft.UpdateServices.Administration.AdminProxy]::GetUpdateServer("localhost", $false, {self.wsus_port});'
            "$updateScope = New-Object Microsoft.UpdateServices.Administration.UpdateScope;"
            "$updateScope.ApprovedStates = [Microsoft.UpdateServices.Administration.ApprovedStates]::Approved;"
            "$updates = $wsus.GetUpdates($updateScope);"
            "$result = @();"
            "foreach($u in $updates){"
            "$result += @{"
            "UpdateId=$u.Id.UpdateId.ToString();"
            "Title=$u.Title;"
            "KbNumber=($u.KnowledgebaseArticles | Select-Object -First 1);"
            "Classification=$u.UpdateClassificationTitle;"
            "Severity=[string]$u.MsrcSeverity;"
            "Products=@($u.ProductTitles);"
            "SecurityBulletins=@($u.SecurityBulletins);"
            "Description=$u.Description;"
            "ArrivalDate=if($u.ArrivalDate){$u.ArrivalDate.ToString('o')}else{''};"
            "}"
            "};"
            "$json = $result | ConvertTo-Json -Depth 3 -AsArray -Compress;"
            "if(-not $json){$json='[]'};"
            "Write-Output $json"
        )

    @staticmethod
    def _parse_updates_json(json_str: str) -> List[WsusUpdate]:
        """解析 PowerShell JSON 输出为 WsusUpdate 列表。"""
        try:
            data = json.loads(json_str.strip())
        except json.JSONDecodeError as exc:
            raise WsusSyncError(f"WSUS PowerShell 输出 JSON 解析失败: {exc}")

        if not isinstance(data, list):
            data = [data]

        updates: List[WsusUpdate] = []
        for item in data:
            kb = item.get("KbNumber") or ""
            if not kb:
                title = item.get("Title") or ""
                kb_match = re.search(r"KB\d{6,}", title)
                kb = kb_match.group(0).upper() if kb_match else ""

            products = item.get("Products") or []
            if isinstance(products, str):
                products = [products]

            security_bulletins = item.get("SecurityBulletins") or []
            if isinstance(security_bulletins, str):
                security_bulletins = [security_bulletins]

            updates.append(WsusUpdate(
                update_id=item.get("UpdateId") or "",
                title=item.get("Title") or "",
                kb_number=kb,
                classification=item.get("Classification") or "",
                severity=item.get("Severity") or "",
                products=products,
                security_bulletins=security_bulletins,
                description=item.get("Description") or "",
                arrival_date=item.get("ArrivalDate") or "",
            ))

            if len(updates) >= MAX_UPDATES:
                break

        logger.info("WsusClient.get_approved_updates: 获取到 %s 条补丁", len(updates))
        return updates


def normalize_wsus_kb(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return f"KB{digits}" if digits else ""


def resolve_wsus_patch(source, update, defaults):
    """按标准化 KB 复用同步补丁；手工补丁冲突时返回 skipped=True。"""
    from apps.patch_mgmt.constants import OSType
    from apps.patch_mgmt.models import Patch, WindowsPatchDetail

    normalized_kb = normalize_wsus_kb(update.kb_number)
    if normalized_kb:
        detail = (
            WindowsPatchDetail.objects.select_related("patch")
            .filter(kb_number__iexact=normalized_kb)
            .first()
        )
        if detail:
            return detail.patch, False, bool(detail.package_file), normalized_kb

    title = (update.kb_number or update.title or update.update_id).strip()
    patch, is_new = Patch.objects.get_or_create(
        title=title,
        os_type=OSType.WINDOWS,
        defaults=defaults,
    )
    return patch, is_new, False, normalized_kb


def sync_wsus(source: PatchSource) -> dict:
    """WSUS 源同步入口：通过 WinRM + PowerShell 拉取补丁元数据。

    流程:
      1. WsusClient.check_connection() -> 连通性检测
      2. WsusClient.get_approved_updates() -> 补丁列表
      3. 每条补丁 -> Patch + WindowsPatchDetail

    Returns:
        {"total": int, "created": int, "updated": int}
    Raises:
        WsusSyncError: 连接失败或同步异常。
    """
    from apps.patch_mgmt.constants import (
        PackageStatus,
        PatchType,
    )
    from apps.patch_mgmt.models import WindowsPatchDetail

    client = WsusClient(source)
    updates = client.get_approved_updates()
    if not updates:
        logger.info("sync_wsus: WSUS 服务器无已批准补丁")
        return {"total": 0, "created": 0, "updated": 0, "skipped": 0}

    sev_map = {
        "critical": "critical",
        "important": "important",
        "moderate": "moderate",
        "low": "low",
        "unspecified": "unspecified",
    }

    created = updated = skipped = 0
    now = timezone.now()

    for upd in updates:
        patch_type = PatchType.SECURITY
        severity = sev_map.get((upd.severity or "").lower(), "unspecified")
        patch, is_new, manual_conflict, normalized_kb = resolve_wsus_patch(
            source,
            upd,
            {
                "patch_type": patch_type,
                "severity": severity,
                "cve_list": [],
                "team": list(source.team or []),
                "pkg_status": PackageStatus.READY,
            },
        )
        if manual_conflict:
            skipped += 1
            logger.info("sync_wsus: 跳过同 KB 手工补丁 kb=%s", normalized_kb)
            continue
        patch.sources.add(source)
        patch.patch_type = patch_type
        patch.severity = severity
        patch.pkg_status = PackageStatus.READY
        patch.last_synced_at = now
        patch.save(update_fields=["patch_type", "severity", "pkg_status", "last_synced_at", "updated_at"])

        WindowsPatchDetail.objects.update_or_create(
            patch=patch,
            defaults={
                "kb_number": normalized_kb,
                "product_list": upd.products or [],
                "ms_bulletin": (upd.security_bulletins[0] if upd.security_bulletins else ""),
            },
        )

        if is_new:
            created += 1
        else:
            updated += 1

    logger.info(
        "sync_wsus: source_id=%s total=%s created=%s updated=%s",
        source.pk, len(updates), created, updated,
    )
    return {
        "total": len(updates),
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }
