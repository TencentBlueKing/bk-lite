"""apt repo 安全补丁同步（网络 I/O 层）。

以 Ubuntu Security Notices (USN) JSON API 为主数据源：
  GET https://ubuntu.com/security/notices.json?release=<codename>&limit=<n>

每条 USN 含 id / title / severity / cves / release_packages，直接映射为
ParsedAdvisory，信息完整度与 yum updateinfo.xml 对齐。

对于非 Ubuntu 发行版（Debian 等），回退到 Packages.gz 索引解析：
  GET <url>/dists/<codename>-security/<component>/binary-<arch>/Packages.gz

Packages.gz 是纯文本索引（非 .deb 二进制），每段含 Package/Version/Architecture/
Description，按空行分割。该文件中的每个包都是安全更新，但无 CVE/严重级别。

本模块执行真实网络 I/O，由 SourceSyncService.sync_linux_repo 调用。
"""

import gzip
import logging
from typing import List, Optional

import requests

from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.services.linux_repo_sync import (
    ParsedAdvisory,
    ParsedPackage,
    RepoSyncError,
)

logger = logging.getLogger("app")

USN_API_URL = "https://ubuntu.com/security/notices.json"
USN_FETCH_TIMEOUT = (5, 30)
USN_PAGE_SIZE = 20
USN_MAX_PAGES = 10

UBUNTU_VERSION_TO_CODENAME = {
    "24.04": "noble",
    "24.10": "oracular",
    "22.04": "jammy",
    "20.04": "focal",
    "18.04": "bionic",
    "16.04": "xenial",
}

DEBIAN_VERSION_TO_CODENAME = {
    "12": "bookworm",
    "11": "bullseye",
    "10": "buster",
}

SEVERITY_MAP = {
    "critical": "Critical",
    "high": "Important",
    "medium": "Moderate",
    "low": "Low",
    "negligible": "Low",
    "untriaged": "",
}


def resolve_codename(source: PatchSource) -> str:
    """从 PatchSource.os_version 解析发行版代号。

    支持直接填代号（jammy）或版本号（22.04）。
    """
    raw = (source.os_version or "").strip().lower()
    if not raw:
        return ""
    if raw in UBUNTU_VERSION_TO_CODENAME.values() or raw in DEBIAN_VERSION_TO_CODENAME.values():
        return raw
    if raw in UBUNTU_VERSION_TO_CODENAME:
        return UBUNTU_VERSION_TO_CODENAME[raw]
    if raw in DEBIAN_VERSION_TO_CODENAME:
        return DEBIAN_VERSION_TO_CODENAME[raw]
    return raw


def fetch_ubuntu_usn(source: PatchSource, codename: str) -> List[ParsedAdvisory]:
    """从 Ubuntu USN JSON API 拉取安全公告（分页拉取，最多 USN_MAX_PAGES 页）。

    Returns:
        ParsedAdvisory 列表。
    Raises:
        RepoSyncError: API 请求失败。
    """
    proxies = _build_proxies(source)
    all_notices = []
    for page in range(USN_MAX_PAGES):
        offset = page * USN_PAGE_SIZE
        try:
            resp = requests.get(
                USN_API_URL,
                params={"release": codename, "limit": USN_PAGE_SIZE, "offset": offset},
                timeout=USN_FETCH_TIMEOUT,
                proxies=proxies,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            if page == 0:
                raise RepoSyncError(f"USN API 请求失败: {exc}")
            logger.warning("fetch_ubuntu_usn: 第 %s 页拉取失败，停止分页: %s", page + 1, exc)
            break

        data = resp.json()
        notices = data.get("notices") or []
        if not notices:
            break
        all_notices.extend(notices)
        total = data.get("total_results", 0)
        if offset + USN_PAGE_SIZE >= total:
            break

    if not all_notices:
        logger.info("fetch_ubuntu_usn: release=%s 无安全公告", codename)
        return []

    advisories: List[ParsedAdvisory] = []
    for notice in notices:
        adv_id = notice.get("id", "").strip()
        if not adv_id:
            continue

        cves_raw = notice.get("cves") or []
        cve_list = [c.get("id", "") for c in cves_raw if isinstance(c, dict) and c.get("id")]

        severity_raw = (notice.get("severity") or "").strip().lower()
        severity = SEVERITY_MAP.get(severity_raw, "")

        release_pkgs = (notice.get("release_packages") or {}).get(codename, [])
        packages: List[ParsedPackage] = []
        for pkg in release_pkgs:
            if not isinstance(pkg, dict):
                continue
            if pkg.get("is_source"):
                continue
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            if not name:
                continue
            packages.append(ParsedPackage(
                name=name,
                version=version,
                arch=source.arch or "all",
            ))

        advisories.append(ParsedAdvisory(
            advisory_id=adv_id,
            title=notice.get("title") or adv_id,
            adv_type="security",
            severity=severity,
            cve_list=cve_list,
            packages=packages,
            issued=notice.get("published"),
        ))

    logger.info("fetch_ubuntu_usn: release=%s 公告数=%s", codename, len(advisories))
    return advisories


def fetch_apt_packages_index(source: PatchSource, codename: str) -> List[ParsedAdvisory]:
    """从 apt repo 的 -security suite 的 Packages.gz 解析安全补丁。

    Packages.gz 中的每个包都是安全更新，但无 CVE/严重级别。
    同时解析 Depends/Conflicts/Breaks/Replaces 作为安装风险信息。

    Returns:
        ParsedAdvisory 列表。
    Raises:
        RepoSyncError: 网络失败或解析失败。
    """
    base = (source.url or "").strip().rstrip("/")
    if not base:
        raise RepoSyncError("补丁源未配置 URL")

    component = "main"
    arch = source.arch or "amd64"
    packages_url = f"{base}/dists/{codename}-security/{component}/binary-{arch}/Packages.gz"

    proxies = _build_proxies(source)
    try:
        resp = requests.get(packages_url, timeout=(5, 30), proxies=proxies)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RepoSyncError(f"拉取 Packages.gz 失败 {packages_url}: {exc}")

    try:
        raw = gzip.decompress(resp.content)
    except OSError as exc:
        raise RepoSyncError(f"Packages.gz 解压失败: {exc}")

    advisories: List[ParsedAdvisory] = []
    for block in raw.decode("utf-8", errors="replace").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        fields: dict[str, str] = {}
        current_key = ""
        for line in block.split("\n"):
            if line.startswith((" ", "\t")) and current_key:
                fields[current_key] += "\n" + line.strip()
            elif ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                fields[key] = value.strip()
                current_key = key

        pkg_name = fields.get("Package", "")
        if not pkg_name:
            continue
        pkg_version = fields.get("Version", "")
        pkg_arch = fields.get("Architecture", arch)

        install_deps = {}
        if fields.get("Depends"):
            install_deps["depends"] = fields["Depends"]
        if fields.get("Pre-Depends"):
            install_deps["pre_depends"] = fields["Pre-Depends"]
        if fields.get("Conflicts"):
            install_deps["conflicts"] = fields["Conflicts"]
        if fields.get("Breaks"):
            install_deps["breaks"] = fields["Breaks"]
        if fields.get("Replaces"):
            install_deps["replaces"] = fields["Replaces"]

        advisories.append(ParsedAdvisory(
            advisory_id=f"{pkg_name}-{pkg_version}",
            title=f"{pkg_name} security update",
            adv_type="security",
            severity="",
            cve_list=[],
            packages=[ParsedPackage(name=pkg_name, version=pkg_version, arch=pkg_arch)],
            issued=None,
            install_deps=install_deps,
        ))

    logger.info("fetch_apt_packages_index: codename=%s 公告数=%s", codename, len(advisories))
    return advisories


def fetch_apt_advisories(source: PatchSource) -> List[ParsedAdvisory]:
    """apt 源安全公告拉取入口。

    直接走 Packages.gz（国内镜像快），不走 USN API（海外慢且不返回 severity）。
    CVE 和 severity 留空，后续可异步丰富。

    Returns:
        ParsedAdvisory 列表。
    Raises:
        RepoSyncError: 拉取失败时抛出。
    """
    codename = resolve_codename(source)
    if not codename:
        raise RepoSyncError(
            "apt 源未配置 os_version，无法确定发行版代号（如 jammy / 22.04）"
        )

    return fetch_apt_packages_index(source, codename)


def _build_proxies(source: PatchSource) -> Optional[dict]:
    if source.proxy_host and source.proxy_port:
        proxy = f"http://{source.proxy_host}:{source.proxy_port}"
        return {"http": proxy, "https": proxy}
    return None
