"""APM 探针制品的系统内存储与下载。

接入脚本从本系统下载离线包，由部署期 `apm_probe_init` 灌入 NATS JetStream
Object Store，避免目标主机依赖公网。
"""

import hashlib
import os
import re
import tempfile
from typing import Iterator

from asgiref.sync import async_to_sync
from nats.js.errors import ObjectNotFoundError

from apps.rpc.jetstream import JetStreamService

JAVA_AGENT_ARTIFACT_NAME = "opentelemetry-javaagent.jar"
PYTHON_WHEELS_ARTIFACT_NAME = "opentelemetry-python-wheels.tar.gz"
NODEJS_AUTO_ARTIFACT_NAME = "opentelemetry-js-auto.tgz"
GO_SDK_ARTIFACT_NAME = "opentelemetry-go-sdk.zip"
DOTNET_AUTO_ARTIFACT_NAME = "opentelemetry-dotnet-auto-linux-glibc-x64.zip"
DOTNET_WINDOWS_ARTIFACT_NAME = "opentelemetry-dotnet-auto-windows.zip"
PHP_AUTO_ARTIFACT_NAME = "opentelemetry-php-auto-linux-glibc-x64.tar.gz"
OBI_ARTIFACT_NAME = "opentelemetry-ebpf-obi-linux-amd64.tar.gz"
RUBY_SDK_ARTIFACT_NAME = "opentelemetry-ruby-sdk.tar.gz"
CPP_SDK_ARTIFACT_NAME = "opentelemetry-cpp-sdk.tar.gz"
ERLANG_SDK_ARTIFACT_NAME = "opentelemetry-erlang-sdk.tar.gz"
SWIFT_SDK_ARTIFACT_NAME = "opentelemetry-swift-sdk.tar.gz"

# 允许对外下载的探针制品白名单；下载接口只接受这里列出的名字，
# 不接受任意对象 key。
PROBE_ARTIFACT_OBJECT_KEYS = {
    JAVA_AGENT_ARTIFACT_NAME: "apm/probe/java/opentelemetry-javaagent.jar",
    PYTHON_WHEELS_ARTIFACT_NAME: "apm/probe/python/opentelemetry-python-wheels.tar.gz",
    NODEJS_AUTO_ARTIFACT_NAME: "apm/probe/nodejs/opentelemetry-js-auto.tgz",
    GO_SDK_ARTIFACT_NAME: "apm/probe/go/opentelemetry-go-sdk.zip",
    DOTNET_AUTO_ARTIFACT_NAME: "apm/probe/dotnet/opentelemetry-dotnet-auto-linux-glibc-x64.zip",
    DOTNET_WINDOWS_ARTIFACT_NAME: "apm/probe/dotnet/opentelemetry-dotnet-auto-windows.zip",
    PHP_AUTO_ARTIFACT_NAME: "apm/probe/php/opentelemetry-php-auto-linux-glibc-x64.tar.gz",
    OBI_ARTIFACT_NAME: "apm/probe/ebpf/opentelemetry-ebpf-obi-linux-amd64.tar.gz",
    RUBY_SDK_ARTIFACT_NAME: "apm/probe/ruby/opentelemetry-ruby-sdk.tar.gz",
    CPP_SDK_ARTIFACT_NAME: "apm/probe/cpp/opentelemetry-cpp-sdk.tar.gz",
    ERLANG_SDK_ARTIFACT_NAME: "apm/probe/erlang/opentelemetry-erlang-sdk.tar.gz",
    SWIFT_SDK_ARTIFACT_NAME: "apm/probe/swift/opentelemetry-swift-sdk.tar.gz",
}

LANGUAGE_PROBE_ARTIFACTS = {
    "java": JAVA_AGENT_ARTIFACT_NAME,
    "python": PYTHON_WHEELS_ARTIFACT_NAME,
    "nodejs": NODEJS_AUTO_ARTIFACT_NAME,
    "go": GO_SDK_ARTIFACT_NAME,
    "dotnet": DOTNET_AUTO_ARTIFACT_NAME,
    "php": PHP_AUTO_ARTIFACT_NAME,
    "obi": OBI_ARTIFACT_NAME,
    "ruby": RUBY_SDK_ARTIFACT_NAME,
    "cpp": CPP_SDK_ARTIFACT_NAME,
    "erlang": ERLANG_SDK_ARTIFACT_NAME,
    "swift": SWIFT_SDK_ARTIFACT_NAME,
}

_EXECUTABLE_PART = re.compile(r"^[A-Za-z0-9._+-]+$")


class ProbeSelectionError(ValueError):
    """接入语言、平台、运行方式或进程路径不能生成片段。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def resolve_probe_artifact_name(language: str, probe_platform: str = "linux") -> str:
    """默认语言映射保持 Linux 制品。.NET Windows 必须显式选择。"""

    if probe_platform not in {"linux", "windows"}:
        raise ProbeSelectionError("probe_platform_invalid")
    if probe_platform == "windows":
        if language != "dotnet":
            raise ProbeSelectionError("probe_platform_unsupported")
        return DOTNET_WINDOWS_ARTIFACT_NAME
    try:
        return LANGUAGE_PROBE_ARTIFACTS[language]
    except KeyError as exc:
        raise ProbeSelectionError("probe_language_unsupported") from exc


def validate_probe_selection(
    *,
    language: str,
    runtime: str,
    probe_platform: str = "linux",
    process_executable: str = "",
) -> str:
    """返回本次片段应下载的制品名。非法组合在生成片段前拒绝。"""

    artifact_name = resolve_probe_artifact_name(language, probe_platform)
    if language == "obi" and runtime != "host":
        raise ProbeSelectionError("obi_runtime_unsupported")
    if language == "dotnet" and probe_platform == "windows" and runtime != "host":
        raise ProbeSelectionError("dotnet_windows_runtime_unsupported")
    if language == "obi":
        if not _is_safe_executable_path(process_executable):
            raise ProbeSelectionError("process_executable_invalid")
    elif process_executable:
        raise ProbeSelectionError("process_executable_unexpected")
    return artifact_name


def _is_safe_executable_path(path: str) -> bool:
    if not path.startswith("/") or path != path.strip():
        return False
    parts = path.split("/")
    if len(parts) < 2 or any(part in {"", ".", ".."} for part in parts[1:]):
        return False
    return all(_EXECUTABLE_PART.fullmatch(part) for part in parts[1:])


# 首版 Java 对象 key，下载时兼容，上传只写新路径。
PROBE_ARTIFACT_LEGACY_OBJECT_KEYS = {
    JAVA_AGENT_ARTIFACT_NAME: "apm/probe/opentelemetry-javaagent.jar",
}

_DOWNLOAD_URL_PATH = "/api/v1/apm/open_api/probe/download"
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_PROBE_ARTIFACT_SHA256_CACHE: dict[str, str] = {}


class ProbeArtifactNotFound(Exception):
    """探针制品不在白名单内，或对象存储中不存在。"""


def build_probe_artifact_download_url(base_url: str, artifact_name: str) -> str:
    if artifact_name not in PROBE_ARTIFACT_OBJECT_KEYS:
        raise ProbeArtifactNotFound(artifact_name)
    return f"{base_url.rstrip('/')}{_DOWNLOAD_URL_PATH}/{artifact_name}"


def get_probe_artifact_sha256(artifact_name: str) -> str:
    """按白名单流式计算制品 SHA-256；同一进程内缓存成功结果。"""
    if artifact_name not in PROBE_ARTIFACT_OBJECT_KEYS:
        raise ProbeArtifactNotFound(artifact_name)
    cached = _PROBE_ARTIFACT_SHA256_CACHE.get(artifact_name)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    stream, _ = open_probe_artifact_stream(artifact_name)
    for chunk in stream:
        digest.update(chunk)
    hex_digest = digest.hexdigest()
    _PROBE_ARTIFACT_SHA256_CACHE[artifact_name] = hex_digest
    return hex_digest


def _object_keys_for_artifact(artifact_name: str) -> tuple[str, ...]:
    object_key = PROBE_ARTIFACT_OBJECT_KEYS.get(artifact_name)
    if object_key is None:
        raise ProbeArtifactNotFound(artifact_name)
    legacy_key = PROBE_ARTIFACT_LEGACY_OBJECT_KEYS.get(artifact_name)
    if legacy_key and legacy_key != object_key:
        return (object_key, legacy_key)
    return (object_key,)


def open_probe_artifact_stream(artifact_name: str) -> tuple[Iterator[bytes], str]:
    """按白名单名字流式读取制品，返回 (chunk 生成器, 文件名)。

    与节点管理安装包下载一致：先落临时文件再分块输出，避免大文件内存堆积。
    """
    object_keys = _object_keys_for_artifact(artifact_name)

    async def _download_to_tempfile():
        jetstream = JetStreamService()
        await jetstream.connect()
        tmp = tempfile.NamedTemporaryFile(mode="w+b", delete=False)
        last_error = None
        try:
            for object_key in object_keys:
                try:
                    await jetstream.object_store.get(object_key, writeinto=tmp)
                    tmp.seek(0)
                    return tmp
                except ObjectNotFoundError as error:
                    last_error = error
                    tmp.seek(0)
                    tmp.truncate(0)
            tmp.close()
            os.unlink(tmp.name)
            raise ProbeArtifactNotFound(artifact_name) from last_error
        except Exception:
            if not tmp.closed:
                tmp.close()
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            raise
        finally:
            await jetstream.close()

    tmp_file = async_to_sync(_download_to_tempfile)()

    def chunk_generator(opened_file):
        try:
            while True:
                chunk = opened_file.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            opened_file.close()
            os.unlink(opened_file.name)

    return chunk_generator(tmp_file), artifact_name


def upload_probe_artifact(artifact_name: str, file_path: str) -> None:
    object_key = PROBE_ARTIFACT_OBJECT_KEYS.get(artifact_name)
    if object_key is None:
        raise ProbeArtifactNotFound(artifact_name)

    async def _upload():
        jetstream = JetStreamService()
        await jetstream.connect()
        try:
            with open(file_path, "rb") as source_file:
                await jetstream.put(object_key, source_file, description=artifact_name)
        finally:
            await jetstream.close()

    async_to_sync(_upload)()
    _PROBE_ARTIFACT_SHA256_CACHE.pop(artifact_name, None)
