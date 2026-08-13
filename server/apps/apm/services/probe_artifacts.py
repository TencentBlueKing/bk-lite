"""APM 探针制品的系统内存储与下载。

探针二进制（当前仅 OpenTelemetry Java Agent）由部署期通过 `apm_probe_init`
管理命令灌入 NATS JetStream Object Store，接入脚本从本系统的免登录下载
地址获取，避免目标主机依赖公网。
"""

import os
import tempfile
from typing import Iterator

from asgiref.sync import async_to_sync
from nats.js.errors import ObjectNotFoundError

from apps.rpc.jetstream import JetStreamService

JAVA_AGENT_ARTIFACT_NAME = "opentelemetry-javaagent.jar"

# 允许对外下载的探针制品白名单；下载接口只接受这里列出的名字，
# 不接受任意对象 key。
PROBE_ARTIFACT_OBJECT_KEYS = {
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


def open_probe_artifact_stream(artifact_name: str) -> tuple[Iterator[bytes], str]:
    """按白名单名字流式读取制品，返回 (chunk 生成器, 文件名)。

    与节点管理安装包下载一致：先落临时文件再分块输出，避免大文件内存堆积。
    """
    object_key = PROBE_ARTIFACT_OBJECT_KEYS.get(artifact_name)
    if object_key is None:
        raise ProbeArtifactNotFound(artifact_name)

    async def _download_to_tempfile():
        jetstream = JetStreamService()
        await jetstream.connect()
        try:
            tmp = tempfile.NamedTemporaryFile(mode="w+b", delete=False)
            try:
                await jetstream.object_store.get(object_key, writeinto=tmp)
            except ObjectNotFoundError as error:
                tmp.close()
                os.unlink(tmp.name)
                raise ProbeArtifactNotFound(artifact_name) from error
            tmp.seek(0)
            return tmp
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
