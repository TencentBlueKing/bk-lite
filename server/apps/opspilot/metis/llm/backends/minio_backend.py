"""MinIOBackend：把 deepagents 文件系统抽象适配到 MinIO 对象存储。

设计要点：
    - 实现 ``BackendProtocol`` 的 6 个低层方法：``ls_info`` / ``read`` /
      ``write`` / ``edit`` / ``grep_raw`` / ``glob_info``。协议自带的
      ``ls()`` / ``grep()`` / ``glob()`` 会委派到这些低层方法，因此实现它们即可。
    - 这是「外部存储」后端：文件真正落到 MinIO bucket，而非 LangGraph state，
      所以 ``write`` / ``edit`` 返回的 ``WriteResult`` / ``EditResult`` 的
      ``files_update`` 恒为 ``None``（不把内容回写进 agent state）。
    - 通过 ``prefix``（namespace）在同一个 bucket 内做多租户隔离：
      虚拟路径 ``/foo/bar.txt`` 会映射为对象 key ``<prefix>/foo/bar.txt``。
    - minio client 通过构造参数注入，便于单测传入内存 fake，无需连接真实 MinIO。

语义尽量与 deepagents 内置的 ``StoreBackend`` 对齐，并直接复用
``deepagents.backends.utils`` 中的工具函数，保证 glob/grep/read 行为一致。
"""

import base64
import logging
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Optional

from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    BackendProtocol,
    EditResult,
    FileData,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import (
    _get_file_type,
    _glob_search_files,
    create_file_data,
    file_data_to_string,
    grep_matches_from_files,
    perform_string_replacement,
    slice_read_response,
    update_file_data,
)

logger = logging.getLogger(__name__)


class MinIOBackend(BackendProtocol):
    """以 MinIO bucket + namespace 前缀为存储的 deepagents 文件后端。"""

    def __init__(
        self,
        bucket_name: str,
        prefix: str = "",
        client: Optional[Any] = None,
        *,
        namespace: Optional[str] = None,
    ) -> None:
        """初始化 MinIOBackend。

        Args:
            bucket_name: MinIO bucket 名称（如 ``munchkin-private``）。
            prefix: 命名空间前缀，用于在同一 bucket 内隔离不同会话 / 智能体。
                例如 ``"agent-files"`` 或 ``"opspilot/<thread_id>"``。
            client: 可注入的 minio SDK client。为 ``None`` 时按需懒加载真实 client
                （从 django_minio_backend / minio 配置构造）。单测请传入内存 fake。
            namespace: ``prefix`` 的别名，二者择一即可（``namespace`` 优先）。
        """
        self._bucket_name = bucket_name
        raw_prefix = namespace if namespace is not None else prefix
        # 归一化：去掉首尾斜杠，统一在内部拼接
        self._prefix = (raw_prefix or "").strip("/")
        self._client = client

    # ------------------------------------------------------------------ #
    # client / key 处理
    # ------------------------------------------------------------------ #
    def _get_client(self):
        """返回 minio SDK client；未注入时懒加载真实 client。"""
        if self._client is not None:
            return self._client
        # 复用 django_minio_backend 已建立的底层 minio client，避免重复配置。
        from django_minio_backend import MinioBackend

        storage = MinioBackend(bucket_name=self._bucket_name)
        # MinioBackend 暴露底层 minio.Minio 实例（属性名随版本可能为 client）。
        client = getattr(storage, "client", None)
        if client is None and hasattr(storage, "get_client"):
            client = storage.get_client()
        if client is None:
            raise RuntimeError("无法获取底层 MinIO client，请显式注入 client 参数。")
        self._client = client
        return client

    def _key_prefix(self) -> str:
        """对象 key 的命名空间前缀（空前缀返回空串，否则带尾斜杠）。"""
        return f"{self._prefix}/" if self._prefix else ""

    def _to_key(self, file_path: str) -> str:
        """虚拟路径 -> 对象 key。"""
        normalized = file_path if file_path.startswith("/") else "/" + file_path
        return self._key_prefix() + normalized.lstrip("/")

    def _to_path(self, key: str) -> Optional[str]:
        """对象 key -> 虚拟路径；不在当前 namespace 下返回 None。"""
        prefix = self._key_prefix()
        if prefix:
            if not key.startswith(prefix):
                return None
            rel = key[len(prefix):]
        else:
            rel = key
        return "/" + rel.lstrip("/")

    # ------------------------------------------------------------------ #
    # 底层对象读写
    # ------------------------------------------------------------------ #
    def _get_object_bytes(self, key: str) -> Optional[bytes]:
        client = self._get_client()
        try:
            resp = client.get_object(self._bucket_name, key)
        except Exception:  # noqa: BLE001  # 任意后端的 NoSuchKey 都视为不存在
            return None
        try:
            return resp.read()
        finally:
            for method in ("close", "release_conn"):
                fn = getattr(resp, method, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:  # noqa: BLE001
                        pass

    def _object_exists(self, key: str) -> bool:
        client = self._get_client()
        try:
            client.stat_object(self._bucket_name, key)
        except Exception:  # noqa: BLE001
            return False
        return True

    def _stat_modified(self, key: str) -> str:
        client = self._get_client()
        try:
            stat = client.stat_object(self._bucket_name, key)
        except Exception:  # noqa: BLE001
            return ""
        return self._format_ts(getattr(stat, "last_modified", None))

    def _put_object_bytes(self, key: str, data: bytes) -> None:
        client = self._get_client()
        client.put_object(self._bucket_name, key, BytesIO(data), length=len(data))

    @staticmethod
    def _format_ts(value: Any) -> str:
        if value is None:
            return ""
        iso = getattr(value, "isoformat", None)
        if callable(iso):
            return iso()
        return str(value)

    def _bytes_to_file_data(self, path: str, data: bytes, last_modified: Any = None) -> FileData:
        """把对象字节转换为 deepagents 的 ``FileData``。"""
        if _get_file_type(path) == "text":
            try:
                content = data.decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                content = base64.standard_b64encode(data).decode("ascii")
                encoding = "base64"
        else:
            content = base64.standard_b64encode(data).decode("ascii")
            encoding = "base64"

        ts = self._format_ts(last_modified)
        fd = FileData(content=content, encoding=encoding)
        # glob/ls 直接访问 modified_at，必须始终提供（缺省空串）。
        fd["modified_at"] = ts
        fd["created_at"] = ts
        return fd

    def _list_objects(self):
        client = self._get_client()
        return list(client.list_objects(self._bucket_name, prefix=self._key_prefix(), recursive=True))

    def _build_files_dict(self) -> dict[str, FileData]:
        """构造 ``{虚拟路径: FileData}`` 映射，供 ls/grep/glob 复用工具函数。"""
        files: dict[str, FileData] = {}
        for obj in self._list_objects():
            key = getattr(obj, "object_name", None)
            if not key:
                continue
            path = self._to_path(key)
            if path is None:
                continue
            data = self._get_object_bytes(key)
            if data is None:
                continue
            files[path] = self._bytes_to_file_data(path, data, getattr(obj, "last_modified", None))
        return files

    def _read_file_data(self, file_path: str) -> Optional[FileData]:
        key = self._to_key(file_path)
        data = self._get_object_bytes(key)
        if data is None:
            return None
        return self._bytes_to_file_data(file_path, data, self._stat_modified(key))

    # ------------------------------------------------------------------ #
    # BackendProtocol 低层方法
    # ------------------------------------------------------------------ #
    def ls_info(self, path: str) -> list[FileInfo]:
        """列出某目录下的文件与一级子目录（非递归）。"""
        files = self._build_files_dict()
        normalized = path if path.endswith("/") else path + "/"

        infos: list[FileInfo] = []
        subdirs: set[str] = set()
        for fpath, fd in files.items():
            if not fpath.startswith(normalized):
                continue
            relative = fpath[len(normalized):]
            if "/" in relative:
                subdirs.add(normalized + relative.split("/")[0] + "/")
                continue
            raw = fd.get("content", "")
            size = len(raw) if isinstance(raw, str) else len("\n".join(raw))
            infos.append(
                {
                    "path": fpath,
                    "is_dir": False,
                    "size": int(size),
                    "modified_at": fd.get("modified_at", ""),
                }
            )

        infos.extend(FileInfo(path=sub, is_dir=True, size=0, modified_at="") for sub in sorted(subdirs))
        infos.sort(key=lambda x: x.get("path", ""))
        return infos

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """读取文件内容（文本按行切片，二进制返回 base64）。"""
        file_data = self._read_file_data(file_path)
        if file_data is None:
            return ReadResult(error=f"File '{file_path}' not found")

        if _get_file_type(file_path) != "text":
            return ReadResult(file_data=file_data)

        sliced = slice_read_response(file_data, offset, limit)
        if isinstance(sliced, ReadResult):
            return sliced
        sliced_fd = FileData(content=sliced, encoding=file_data.get("encoding", "utf-8"))
        if "created_at" in file_data:
            sliced_fd["created_at"] = file_data["created_at"]
        if "modified_at" in file_data:
            sliced_fd["modified_at"] = file_data["modified_at"]
        return ReadResult(file_data=sliced_fd)

    def write(self, file_path: str, content: str) -> WriteResult:
        """新建文件，已存在则报错。外部存储，files_update 恒为 None。"""
        key = self._to_key(file_path)
        if self._object_exists(key):
            return WriteResult(
                error=(
                    f"Cannot write to {file_path} because it already exists. "
                    f"Read and then make an edit, or write to a new path."
                )
            )
        file_data = create_file_data(content)
        self._put_object_bytes(key, file_data["content"].encode("utf-8"))
        return WriteResult(path=file_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """对已存在文件做精确字符串替换。外部存储，files_update 恒为 None。"""
        file_data = self._read_file_data(file_path)
        if file_data is None:
            return EditResult(error=f"Error: File '{file_path}' not found")

        content = file_data_to_string(file_data)
        result = perform_string_replacement(content, old_string, new_string, replace_all)
        if isinstance(result, str):
            return EditResult(error=result)

        new_content, occurrences = result
        new_file_data = update_file_data(file_data, new_content)
        self._put_object_bytes(self._to_key(file_path), new_file_data["content"].encode("utf-8"))
        return EditResult(path=file_path, occurrences=int(occurrences))

    def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
    ):
        """字面量文本搜索（非正则），返回匹配列表或错误字符串。"""
        files = self._build_files_dict()
        result = grep_matches_from_files(files, pattern, path, glob)
        if result.error is not None:
            return result.error
        matches: list[GrepMatch] = result.matches or []
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """按 glob 模式匹配文件，返回 FileInfo 列表。"""
        files = self._build_files_dict()
        result = _glob_search_files(files, pattern, path)
        if result == "No files found":
            return []

        infos: list[FileInfo] = []
        for p in result.split("\n"):
            fd = files.get(p)
            if fd:
                raw = fd.get("content", "")
                size = len(raw) if isinstance(raw, str) else len("\n".join(raw))
                modified_at = fd.get("modified_at", "")
            else:
                size = 0
                modified_at = ""
            infos.append(
                {
                    "path": p,
                    "is_dir": False,
                    "size": int(size),
                    "modified_at": modified_at,
                }
            )
        return infos

    # ------------------------------------------------------------------ #
    # 批量上传 / 下载（SkillsMiddleware 依赖 download_files 加载 SKILL.md）
    # ------------------------------------------------------------------ #
    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量下载文件原始字节；缺失文件返回 ``file_not_found``。

        deepagents 的 ``SkillsMiddleware`` 通过 ``ls`` 找到各技能目录后，调用
        本方法批量读取 ``SKILL.md`` 的原始内容（bytes）做 frontmatter 解析。
        """
        responses: list[FileDownloadResponse] = []
        for file_path in paths:
            data = self._get_object_bytes(self._to_key(file_path))
            if data is None:
                responses.append(FileDownloadResponse(path=file_path, content=None, error=FILE_NOT_FOUND))
            else:
                responses.append(FileDownloadResponse(path=file_path, content=data, error=None))
        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量上传文件原始字节（覆盖写）。"""
        responses: list[FileUploadResponse] = []
        for file_path, content in files:
            try:
                self._put_object_bytes(self._to_key(file_path), content)
                responses.append(FileUploadResponse(path=file_path, error=None))
            except Exception as exc:  # noqa: BLE001
                responses.append(FileUploadResponse(path=file_path, error=str(exc)))
        return responses
