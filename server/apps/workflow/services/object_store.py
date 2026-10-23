from __future__ import annotations

from asgiref.sync import async_to_sync

from apps.node_mgmt.utils.s3 import delete_s3_file, download_file_by_s3, upload_file_to_s3

MAX_ARTIFACT_DOWNLOAD_BYTES = 50 * 1024 * 1024


class ArtifactTooLarge(ValueError):
    """Artifact content exceeds the download size limit."""


class WorkflowObjectStore:
    """编排中心对象存储 Adapter；对象内容不进入数据库。"""

    def put(self, key: str, content) -> None:
        async_to_sync(upload_file_to_s3)(content, key)

    def get(self, key: str, *, max_bytes: int | None = MAX_ARTIFACT_DOWNLOAD_BYTES) -> tuple[bytes, str, int]:
        payload = async_to_sync(download_file_by_s3)(key)
        if isinstance(payload, tuple) and len(payload) == 3:
            content, filename, size = payload
            content = bytes(content)
            if max_bytes is not None and len(content) > max_bytes:
                raise ArtifactTooLarge("报告文件超过下载大小限制")
            return content, filename or key.rsplit("/", 1)[-1], int(size) if size else len(content)
        if isinstance(payload, tuple) and len(payload) == 2:
            data, filename = payload
            content = bytes(data)
            if max_bytes is not None and len(content) > max_bytes:
                raise ArtifactTooLarge("报告文件超过下载大小限制")
            return content, filename or key.rsplit("/", 1)[-1], len(content)
        data = getattr(payload, "data", payload)
        if hasattr(data, "read"):
            data = data.read()
        content = bytes(data)
        if max_bytes is not None and len(content) > max_bytes:
            raise ArtifactTooLarge("报告文件超过下载大小限制")
        return content, key.rsplit("/", 1)[-1], len(content)

    def delete(self, key: str) -> None:
        async_to_sync(delete_s3_file)(key)
