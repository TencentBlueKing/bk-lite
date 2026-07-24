"""补丁源连通性真实探测（网络 I/O 层）。

与其他 service（纯数据/编排，无网络 I/O）不同，本模块**执行真实 HTTP 网络 I/O**，
是连通性探测的实际执行点。由 Celery 任务 check_patch_source_connectivity 调用，
探测结果经 SourceSyncService.record_connectivity_result 写回 PatchSource。

探测策略（仅针对配置了 URL 的源）：
  - yum/dnf repo：GET <url>/repodata/repomd.xml（同时校验是有效 repo）
  - apt repo：GET <url>/dists/（检查 apt 仓库结构目录存在）
  - WSUS：SOAP GetUpdateServerStatus（协议级校验）

判定：HTTP 状态码 < 400 视为可达（2xx/3xx）；>=400（如 404 repomd 不存在）或
网络异常（超时、DNS、连接拒绝）视为不可达。

无 URL 的源（如未填 URL 的 WSUS）无法探测，返回 None（调用方保持 UNKNOWN）。
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests

from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource

logger = logging.getLogger("app")

# (连接超时, 读取超时) —— 硬封顶，避免探测无限阻塞请求/worker。
PROBE_CONNECT_TIMEOUT = 5
PROBE_READ_TIMEOUT = 8
PROBE_TIMEOUT = (PROBE_CONNECT_TIMEOUT, PROBE_READ_TIMEOUT)


@dataclass(frozen=True)
class ProbeResult:
    """连通性探测结果。"""

    reachable: bool
    status_code: Optional[int]
    detail: str


def _build_probe_url(source: PatchSource, url: str) -> str:
    """按源类型构造探测目标 URL。"""
    base = url.rstrip("/")
    if source.source_type in (PatchSourceType.YUM_REPO, PatchSourceType.DNF_REPO):
        return f"{base}/repodata/repomd.xml"
    if source.source_type == PatchSourceType.APT_REPO:
        codename = _resolve_apt_codename(source.os_version)
        return f"{base}/dists/{codename}/InRelease"
    # 其他源：探测配置的基址。
    return url


def _resolve_apt_codename(os_version: str) -> str:
    value = (os_version or "").strip().lower()
    codenames = {
        "18.04": "bionic",
        "20.04": "focal",
        "22.04": "jammy",
        "24.04": "noble",
        "10": "buster",
        "11": "bullseye",
        "12": "bookworm",
    }
    if value in codenames:
        return codenames[value]
    if value and value.replace("-", "").isalpha():
        return value
    raise ValueError("APT 源必须填写可识别的系统版本或发行代号")


def _build_proxies(source: PatchSource) -> Optional[dict]:
    """补丁源可按配置通过代理访问。"""
    if source.proxy_host and source.proxy_port:
        proxy = f"http://{source.proxy_host}:{source.proxy_port}"
        return {"http": proxy, "https": proxy}
    return None


def _build_auth(source: PatchSource):
    """WSUS 等可选基础认证。"""
    if source.auth_user:
        return (source.auth_user, source.get_auth_password())
    return None


def _valid_repository_metadata(source: PatchSource, content: bytes) -> bool:
    sample = (content or b"")[:131072].lower()
    if source.source_type in (PatchSourceType.YUM_REPO, PatchSourceType.DNF_REPO):
        return b"<repomd" in sample
    if source.source_type == PatchSourceType.APT_REPO:
        return b"origin:" in sample and (b"suite:" in sample or b"codename:" in sample)
    return True


def probe_source(source: PatchSource) -> Optional[ProbeResult]:
    """对补丁源发起真实 HTTP/SOAP 探测。

    Returns:
        ProbeResult：探测已执行（reachable 表示是否可达）。
        None：源未配置 URL，无法探测（调用方应保持 UNKNOWN）。
    """
    url = (source.url or "").strip()
    if not url:
        logger.info("probe_source: source_id=%s 未配置 URL，跳过探测", source.pk)
        return None

    # WSUS：用 SOAP GetUpdateServerStatus 做协议级检测
    if source.source_type == PatchSourceType.WSUS:
        return _probe_wsus(source)

    try:
        target = _build_probe_url(source, url)
    except ValueError as exc:
        return ProbeResult(reachable=False, status_code=None, detail=str(exc))
    proxies = _build_proxies(source)
    auth = _build_auth(source)

    try:
        resp = requests.get(
            target,
            timeout=PROBE_TIMEOUT,
            proxies=proxies,
            auth=auth,
            allow_redirects=True,
            stream=False,
        )
        if (
            source.source_type == PatchSourceType.APT_REPO
            and resp.status_code == 404
            and target.endswith("/InRelease")
        ):
            resp.close()
            target = target.removesuffix("/InRelease") + "/Release"
            resp = requests.get(
                target,
                timeout=PROBE_TIMEOUT,
                proxies=proxies,
                auth=auth,
                allow_redirects=True,
                stream=False,
            )
        content = resp.content
        resp.close()
        reachable = resp.status_code < 400 and _valid_repository_metadata(source, content)
        detail = f"GET {target} -> {resp.status_code}"
        if resp.status_code < 400 and not reachable:
            detail += "，仓库元数据格式无效"
        logger.info("probe_source: source_id=%s %s reachable=%s", source.pk, detail, reachable)
        return ProbeResult(reachable=reachable, status_code=resp.status_code, detail=detail)
    except requests.RequestException as exc:
        detail = f"GET {target} 失败: {exc}"
        logger.warning("probe_source: source_id=%s %s", source.pk, detail)
        return ProbeResult(reachable=False, status_code=None, detail=detail)


def _probe_wsus(source: PatchSource) -> ProbeResult:
    """WSUS 连通性探测：WinRM + PowerShell AdminProxy.GetUpdateServer()。

    优先做 PowerShell 协议级检测；如果失败但 HTTP 基址可达，
    降级为 reachable=True（服务器在线但 WinRM 可能未配置）。
    """
    from apps.patch_mgmt.services.wsus_sync import WsusClient, WsusSyncError

    try:
        client = WsusClient(source)
        if client.check_connection():
            return ProbeResult(
                reachable=True,
                status_code=200,
                detail="WSUS WinRM PowerShell AdminProxy 认证成功",
            )
    except WsusSyncError as exc:
        logger.warning("_probe_wsus: WinRM 检测失败 source_id=%s: %s", source.pk, exc)
    return ProbeResult(
        reachable=False,
        status_code=None,
        detail="WSUS WinRM PowerShell AdminProxy 认证失败",
    )
