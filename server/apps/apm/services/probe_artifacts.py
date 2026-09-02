"""APM 探针制品的系统内存储与下载。

本版本可用的 Java / Python / Node.js / Go / .NET 接入脚本都从本系统下载离线包，
由部署期 `apm_probe_init` 灌入 NATS JetStream Object Store，避免目标主机
依赖公网。
"""

import os
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

# 允许对外下载的探针制品白名单；下载接口只接受这里列出的名字，
# 不接受任意对象 key。
PROBE_ARTIFACT_OBJECT_KEYS = {
    JAVA_AGENT_ARTIFACT_NAME: "apm/probe/java/opentelemetry-javaagent.jar",
    PYTHON_WHEELS_ARTIFACT_NAME: "apm/probe/python/opentelemetry-python-wheels.tar.gz",
    NODEJS_AUTO_ARTIFACT_NAME: "apm/probe/nodejs/opentelemetry-js-auto.tgz",
    GO_SDK_ARTIFACT_NAME: "apm/probe/go/opentelemetry-go-sdk.zip",
    DOTNET_AUTO_ARTIFACT_NAME: "apm/probe/dotnet/opentelemetry-dotnet-auto-linux-glibc-x64.zip",
}

LANGUAGE_PROBE_ARTIFACTS = {
    "java": JAVA_AGENT_ARTIFACT_NAME,
    "python": PYTHON_WHEELS_ARTIFACT_NAME,
    "nodejs": NODEJS_AUTO_ARTIFACT_NAME,
    "go": GO_SDK_ARTIFACT_NAME,
    "dotnet": DOTNET_AUTO_ARTIFACT_NAME,
}

# 首版 Java 对象 key，下载时兼容，上传只写新路径。
PROBE_ARTIFACT_LEGACY_OBJECT_KEYS = {
    JAVA_AGENT_ARTIFACT_NAME: "apm/probe/opentelemetry-javaagent.jar",
}

_DOWNLOAD_URL_PATH = "/api/v1/apm/open_api/probe/download"
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class ProbeArtifactNotFound(Exception):
    """探针制品不在白名单内，或对象存储中不存在。"""


def build_probe_artifact_download_url(base_url: str, artifact_name: str) -> str:
    if artifact_name not in PROBE_ARTIFACT_OBJECT_KEYS:
        raise ProbeArtifactNotFound(artifact_name)
    return f"{base_url.rstrip('/')}{_DOWNLOAD_URL_PATH}/{artifact_name}"


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
