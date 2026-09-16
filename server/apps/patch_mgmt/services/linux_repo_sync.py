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
import io
from dataclasses import dataclass, field
from typing import List, Optional
from xml.etree import ElementTree as ET

import requests
from apps.core.logger import patch_mgmt_logger as logger
from apps.patch_mgmt.config import (
    LINUX_REPO_SYNC_MAX_ADVISORIES,
    LINUX_REPO_SYNC_MAX_COMPRESSED_BYTES,
    LINUX_REPO_SYNC_MAX_PACKAGES_PER_ADVISORY,
    LINUX_REPO_SYNC_MAX_UNCOMPRESSED_BYTES,
)
from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.utils.architecture import (
    X86_64,
    normalize_architecture,
    repository_package_applies,
)

FETCH_TIMEOUT = (5, 30)  # (连接, 读取) 秒
_CHUNK_SIZE = 64 * 1024


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


def _build_proxies(source: PatchSource) -> Optional[dict]:
    if source.proxy_host and source.proxy_port:
        proxy = f"http://{source.proxy_host}:{source.proxy_port}"
        return {"http": proxy, "https": proxy}
    return None


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


class _BoundedReader:
    """按解压后累计字节截断的只读流，避免 gzip.decompress 一次展开。"""

    def __init__(self, inner, max_bytes: int, message: str):
        self._inner = inner
        self._max_bytes = max_bytes
        self._message = message
        self._total = 0

    def read(self, size: int = -1) -> bytes:
        data = self._inner.read(size)
        if data:
            self._total += len(data)
            if self._total > self._max_bytes:
                raise RepoSyncError(self._message)
        return data


def _read_bounded_content(resp, max_bytes: int, url: str) -> bytes:
    content = bytearray()
    for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > max_bytes:
            raise RepoSyncError(f"拉取失败 {url}: 元数据压缩体积超过上限 {max_bytes} 字节")
    return bytes(content)


def _get(url: str, source: PatchSource) -> bytes:
    try:
        resp = requests.get(
            url,
            timeout=FETCH_TIMEOUT,
            proxies=_build_proxies(source),
            stream=True,
        )
    except requests.RequestException as exc:
        raise RepoSyncError(f"拉取失败 {url}: {exc}") from exc
    try:
        resp.raise_for_status()
        return _read_bounded_content(resp, LINUX_REPO_SYNC_MAX_COMPRESSED_BYTES, url)
    except requests.RequestException as exc:
        raise RepoSyncError(f"拉取失败 {url}: {exc}") from exc
    finally:
        resp.close()


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


def _parse_one_update(upd) -> Optional[ParsedAdvisory]:
    adv_id = (upd.findtext("{*}id") or "").strip()
    if not adv_id:
        return None
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
    max_packages = LINUX_REPO_SYNC_MAX_PACKAGES_PER_ADVISORY
    pkglist = upd.find("{*}pkglist")
    if pkglist is not None:
        for col in pkglist.findall("{*}collection"):
            for pkg in col.findall("{*}package"):
                if len(packages) >= max_packages:
                    raise RepoSyncError(f"单条公告软件包数量超过上限 {max_packages}")
                ver = pkg.get("version", "")
                rel = pkg.get("release", "")
                packages.append(ParsedPackage(
                    name=pkg.get("name", ""),
                    version=f"{ver}-{rel}".strip("-"),
                    arch=pkg.get("arch", ""),
                ))

    issued_el = upd.find("{*}issued")
    issued = issued_el.get("date") if issued_el is not None else None

    return ParsedAdvisory(
        advisory_id=adv_id,
        title=title,
        adv_type=upd.get("type", ""),
        severity=severity,
        cve_list=cve_list,
        packages=packages,
        issued=issued,
    )


def _parse_updateinfo(xml_file) -> List[ParsedAdvisory]:
    advisories: List[ParsedAdvisory] = []
    max_advisories = LINUX_REPO_SYNC_MAX_ADVISORIES
    try:
        for _event, elem in ET.iterparse(xml_file, events=("end",)):
            if _local_name(elem.tag) != "update":
                continue
            advisory = _parse_one_update(elem)
            elem.clear()
            if advisory is None:
                continue
            if len(advisories) >= max_advisories:
                raise RepoSyncError(f"安全公告数量超过上限 {max_advisories}")
            advisories.append(advisory)
    except ET.ParseError as exc:
        raise RepoSyncError(f"updateinfo 解析失败: {exc}") from exc
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

    repomd = _get(f"{base}/repodata/repomd.xml", source)
    href = _find_updateinfo_href(repomd)
    if not href:
        logger.info("fetch_advisories: source_id=%s repo 无 updateinfo", source.pk)
        return []

    data = _get(f"{base}/{href}", source)
    max_uncompressed = LINUX_REPO_SYNC_MAX_UNCOMPRESSED_BYTES
    try:
        if href.endswith(".gz"):
            xml_source = _BoundedReader(
                gzip.GzipFile(fileobj=io.BytesIO(data)),
                max_uncompressed,
                f"元数据解压体积超过上限 {max_uncompressed} 字节",
            )
        else:
            if len(data) > max_uncompressed:
                raise RepoSyncError(f"元数据解压体积超过上限 {max_uncompressed} 字节")
            xml_source = io.BytesIO(data)
        parsed_advisories = _parse_updateinfo(xml_source)
    except RepoSyncError:
        raise
    except (OSError, EOFError) as exc:
        raise RepoSyncError(f"updateinfo 解压失败: {exc}") from exc
    canonical_arch = normalize_architecture(source.arch, default=X86_64)
    advisories = []
    for advisory in parsed_advisories:
        applicable_packages = []
        for package in advisory.packages:
            if not repository_package_applies(
                package.arch,
                source_type=source.source_type,
                target_architecture=canonical_arch,
            ):
                continue
            package.arch = canonical_arch
            applicable_packages.append(package)
        if not applicable_packages:
            continue
        advisory.packages = applicable_packages
        advisories.append(advisory)
    return advisories
