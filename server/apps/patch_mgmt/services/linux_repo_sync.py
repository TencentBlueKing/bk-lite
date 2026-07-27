"""Linux yum/dnf/apt repo 补丁元数据同步(网络 I/O 层)。

对接真实 repo,拉取并解析安全公告元数据,产出补丁档案数据。
**仅元数据,不下载包文件**(包在安装时由 Linux 插件从 repo 解析获取)。

流程(yum/dnf):
  <url>/repodata/repomd.xml  -> 找 type=updateinfo 的 location
  -> 下载 updateinfo.xml(.gz) -> gunzip -> 解析每个 <update> 为一条补丁。

流程(apt):
  委托 apt_sync 模块处理（Ubuntu USN JSON API + Packages.gz 回退）。

说明:
  - apt repo 无统一的 updateinfo 元数据,改用 USN API / Packages.gz 索引。
  - repo 无 updateinfo(纯软件包仓库、无安全公告)时返回空,不报错。
  - 与其他 service 不同,本模块执行真实网络 I/O,由 SourceSyncService 调用。
"""

import gzip
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from xml.etree import ElementTree as ET

import requests

from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource

logger = logging.getLogger("app")

FETCH_TIMEOUT = (5, 30)  # (连接, 读取) 秒


class RepoSyncError(Exception):
    """repo 同步异常(网络/解析)。"""


@dataclass
class ParsedPackage:
    name: str
    version: str
    arch: str


@dataclass
class ParsedAdvisory:
    advisory_id: str
    title: str
    adv_type: str  # security / bugfix / enhancement
    severity: str  # Critical/Important/Moderate/Low 或 ''
    cve_list: List[str] = field(default_factory=list)
    packages: List[ParsedPackage] = field(default_factory=list)
    issued: Optional[str] = None
    install_deps: dict = field(default_factory=dict)  # apt: {depends, conflicts, breaks, replaces}


def _get(url: str) -> bytes:
    try:
        resp = requests.get(url, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as exc:
        raise RepoSyncError(f"拉取失败 {url}: {exc}")


def _find_updateinfo_href(repomd_bytes: bytes) -> Optional[str]:
    """从 repomd.xml 找 type=updateinfo 的 location href。"""
    try:
        root = ET.fromstring(repomd_bytes)
    except ET.ParseError as exc:
        raise RepoSyncError(f"repomd.xml 解析失败: {exc}")
    for data in root.findall("{*}data"):
        if data.get("type") == "updateinfo":
            loc = data.find("{*}location")
            if loc is not None:
                return loc.get("href")
    return None


def _parse_updateinfo(xml_bytes: bytes) -> List[ParsedAdvisory]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise RepoSyncError(f"updateinfo 解析失败: {exc}")

    advisories: List[ParsedAdvisory] = []
    for upd in root.findall("{*}update"):
        adv_id = (upd.findtext("{*}id") or "").strip()
        if not adv_id:
            continue
        title = (upd.findtext("{*}title") or "").strip() or adv_id
        severity = (upd.findtext("{*}severity") or "").strip()
        if severity.lower() == "none":
            severity = ""

        cve_list: List[str] = []
        refs = upd.find("{*}references")
        if refs is not None:
            for ref in refs.findall("{*}reference"):
                if (ref.get("type") or "").lower() == "cve":
                    cid = ref.get("id") or ref.get("title")
                    if cid:
                        cve_list.append(cid)

        packages: List[ParsedPackage] = []
        pkglist = upd.find("{*}pkglist")
        if pkglist is not None:
            for col in pkglist.findall("{*}collection"):
                for pkg in col.findall("{*}package"):
                    ver = pkg.get("version", "")
                    rel = pkg.get("release", "")
                    packages.append(ParsedPackage(
                        name=pkg.get("name", ""),
                        version=f"{ver}-{rel}".strip("-"),
                        arch=pkg.get("arch", ""),
                    ))

        issued_el = upd.find("{*}issued")
        issued = issued_el.get("date") if issued_el is not None else None

        advisories.append(ParsedAdvisory(
            advisory_id=adv_id,
            title=title,
            adv_type=upd.get("type", ""),
            severity=severity,
            cve_list=cve_list,
            packages=packages,
            issued=issued,
        ))

    return advisories


def fetch_advisories(source: PatchSource) -> List[ParsedAdvisory]:
    """拉取并解析补丁源的安全公告。

    - yum/dnf：解析 repo updateinfo.xml
    - apt：走 apt_sync 模块（USN API + Packages.gz 回退）

    Returns:
        ParsedAdvisory 列表;无数据时返回 []。
    Raises:
        RepoSyncError: 未配置 URL、网络失败或解析失败。
    """
    if source.source_type == PatchSourceType.APT_REPO:
        from apps.patch_mgmt.services.apt_sync import fetch_apt_advisories

        return fetch_apt_advisories(source)

    if source.source_type not in (PatchSourceType.YUM_REPO, PatchSourceType.DNF_REPO):
        logger.info("fetch_advisories: %s 非 yum/dnf/apt,跳过", source.source_type)
        return []

    base = (source.url or "").strip().rstrip("/")
    if not base:
        raise RepoSyncError("补丁源未配置 URL")

    repomd = _get(f"{base}/repodata/repomd.xml")
    href = _find_updateinfo_href(repomd)
    if not href:
        logger.info("fetch_advisories: source_id=%s repo 无 updateinfo", source.pk)
        return []

    data = _get(f"{base}/{href}")
    if href.endswith(".gz"):
        try:
            data = gzip.decompress(data)
        except OSError as exc:
            raise RepoSyncError(f"updateinfo 解压失败: {exc}")
    return _parse_updateinfo(data)
