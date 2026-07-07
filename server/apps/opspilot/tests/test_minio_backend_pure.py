"""MinIOBackend 纯单元测试（无 DB / 无网络 / 无真实 MinIO）。

使用内存 fake minio client 覆盖 6 个低层方法（ls_info / read / write /
edit / grep_raw / glob_info），以及外部存储 files_update=None 约定、
namespace/prefix 隔离与 glob/grep 行为。

运行（隔离、无 coverage/db 插件）：
    uv run pytest apps/opspilot/tests/test_minio_backend_pure.py \
        -p no:cacheprovider -o addopts="" -q
"""

import base64
from datetime import datetime, timezone
from io import BytesIO

import pytest

from apps.opspilot.metis.llm.backends.minio_backend import MinIOBackend


# --------------------------------------------------------------------------- #
# 内存 fake minio client，模拟 minio SDK 的 list/get/stat/put/remove 接口
# --------------------------------------------------------------------------- #
class _FakeObject:
    def __init__(self, object_name, size, last_modified=None):
        self.object_name = object_name
        self.size = size
        self.last_modified = last_modified


class _FakeResponse:
    def __init__(self, data):
        self._data = data
        self.closed = False
        self.conn_released = False

    def read(self):
        return self._data

    def close(self):
        self.closed = True

    def release_conn(self):
        self.conn_released = True


class _NoSuchKey(Exception):
    """模拟 minio.error.S3Error(NoSuchKey)。"""


class FakeMinioClient:
    def __init__(self, initial=None):
        # key(str) -> bytes
        self.store = dict(initial or {})

    def list_objects(self, bucket_name, prefix="", recursive=False):
        for key in sorted(self.store):
            if key.startswith(prefix):
                yield _FakeObject(key, len(self.store[key]), datetime.now(timezone.utc))

    def get_object(self, bucket_name, object_name):
        if object_name not in self.store:
            raise _NoSuchKey(object_name)
        return _FakeResponse(self.store[object_name])

    def stat_object(self, bucket_name, object_name):
        if object_name not in self.store:
            raise _NoSuchKey(object_name)
        return _FakeObject(object_name, len(self.store[object_name]), datetime.now(timezone.utc))

    def put_object(self, bucket_name, object_name, data, length=-1, **kwargs):
        raw = data.read() if hasattr(data, "read") else data
        self.store[object_name] = raw
        return _FakeObject(object_name, len(raw))

    def remove_object(self, bucket_name, object_name):
        self.store.pop(object_name, None)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def client():
    return FakeMinioClient()


@pytest.fixture
def backend(client):
    return MinIOBackend(bucket_name="munchkin-private", prefix="agent-files", client=client)


def _seed(client, prefix, path, content):
    key = f"{prefix.strip('/')}/{path.lstrip('/')}"
    client.store[key] = content.encode("utf-8") if isinstance(content, str) else content


# --------------------------------------------------------------------------- #
# write
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_write_creates_object_with_namespaced_key(backend, client):
    result = backend.write("/notes/todo.txt", "hello world")
    assert result.error is None
    assert result.path == "/notes/todo.txt"
    # 对象 key 应带 prefix 命名空间
    assert client.store["agent-files/notes/todo.txt"] == b"hello world"


@pytest.mark.unit
def test_write_external_storage_files_update_is_none(backend):
    result = backend.write("/a.txt", "x")
    assert result.files_update is None


@pytest.mark.unit
def test_write_existing_file_errors(backend):
    backend.write("/dup.txt", "first")
    result = backend.write("/dup.txt", "second")
    assert result.error is not None
    assert result.path is None


# --------------------------------------------------------------------------- #
# read
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_read_returns_file_data(backend, client):
    _seed(client, "agent-files", "/doc.txt", "line1\nline2\nline3")
    result = backend.read("/doc.txt")
    assert result.error is None
    assert result.file_data is not None
    assert "line1" in result.file_data["content"]
    assert result.file_data["encoding"] == "utf-8"


@pytest.mark.unit
def test_read_missing_file_returns_error(backend):
    result = backend.read("/nope.txt")
    assert result.error is not None
    assert result.file_data is None


@pytest.mark.unit
def test_read_offset_and_limit(backend, client):
    _seed(client, "agent-files", "/multi.txt", "a\nb\nc\nd\ne")
    result = backend.read("/multi.txt", offset=1, limit=2)
    assert result.error is None
    assert result.file_data["content"] == "b\nc\n"


@pytest.mark.unit
def test_read_binary_file_returns_base64(backend, client):
    raw = b"\x89PNG\r\n\x1a\n\x00\xffbinary"
    client.store["agent-files/img.png"] = raw
    result = backend.read("/img.png")
    assert result.error is None
    assert result.file_data["encoding"] == "base64"
    assert base64.standard_b64decode(result.file_data["content"]) == raw


# --------------------------------------------------------------------------- #
# edit
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_edit_replaces_content(backend, client):
    backend.write("/cfg.txt", "foo=1\nbar=2\n")
    result = backend.edit("/cfg.txt", "bar=2", "bar=9")
    assert result.error is None
    assert result.occurrences == 1
    assert client.store["agent-files/cfg.txt"] == b"foo=1\nbar=9\n"


@pytest.mark.unit
def test_edit_external_storage_files_update_is_none(backend):
    backend.write("/cfg.txt", "abc")
    result = backend.edit("/cfg.txt", "abc", "xyz")
    assert result.files_update is None


@pytest.mark.unit
def test_edit_missing_file_errors(backend):
    result = backend.edit("/ghost.txt", "a", "b")
    assert result.error is not None
    assert result.path is None


@pytest.mark.unit
def test_edit_non_unique_without_replace_all_errors(backend):
    backend.write("/r.txt", "x\nx\nx")
    result = backend.edit("/r.txt", "x", "y")
    assert result.error is not None


@pytest.mark.unit
def test_edit_replace_all(backend, client):
    backend.write("/r.txt", "x\nx\nx")
    result = backend.edit("/r.txt", "x", "y", replace_all=True)
    assert result.error is None
    assert result.occurrences == 3
    assert client.store["agent-files/r.txt"] == b"y\ny\ny"


# --------------------------------------------------------------------------- #
# ls_info
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_ls_info_lists_files_and_subdirs(backend, client):
    _seed(client, "agent-files", "/a.txt", "1")
    _seed(client, "agent-files", "/b.txt", "22")
    _seed(client, "agent-files", "/sub/c.txt", "333")
    entries = backend.ls_info("/")
    paths = {e["path"] for e in entries}
    assert "/a.txt" in paths
    assert "/b.txt" in paths
    # 子目录被聚合为 dir 条目（带尾斜杠）
    assert "/sub/" in paths
    sub = next(e for e in entries if e["path"] == "/sub/")
    assert sub["is_dir"] is True
    a = next(e for e in entries if e["path"] == "/a.txt")
    assert a["is_dir"] is False
    assert a["size"] == 1


@pytest.mark.unit
def test_ls_info_subdirectory(backend, client):
    _seed(client, "agent-files", "/sub/c.txt", "hello")
    _seed(client, "agent-files", "/sub/d.txt", "world")
    entries = backend.ls_info("/sub")
    paths = {e["path"] for e in entries}
    assert paths == {"/sub/c.txt", "/sub/d.txt"}


# --------------------------------------------------------------------------- #
# grep_raw
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_grep_raw_finds_matches(backend, client):
    _seed(client, "agent-files", "/log1.txt", "INFO ok\nERROR boom\nINFO done")
    _seed(client, "agent-files", "/log2.txt", "all good")
    matches = backend.grep_raw("ERROR")
    assert isinstance(matches, list)
    assert len(matches) == 1
    m = matches[0]
    assert m["path"] == "/log1.txt"
    assert m["line"] == 2
    assert "ERROR" in m["text"]


@pytest.mark.unit
def test_grep_raw_with_glob_filter(backend, client):
    _seed(client, "agent-files", "/a.py", "needle here")
    _seed(client, "agent-files", "/b.txt", "needle there")
    matches = backend.grep_raw("needle", glob="*.py")
    assert isinstance(matches, list)
    assert len(matches) == 1
    assert matches[0]["path"] == "/a.py"


# --------------------------------------------------------------------------- #
# glob_info
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_glob_info_matches_pattern(backend, client):
    _seed(client, "agent-files", "/x.py", "1")
    _seed(client, "agent-files", "/y.py", "2")
    _seed(client, "agent-files", "/z.txt", "3")
    infos = backend.glob_info("*.py", "/")
    paths = {i["path"] for i in infos}
    assert paths == {"/x.py", "/y.py"}


@pytest.mark.unit
def test_glob_info_recursive(backend, client):
    _seed(client, "agent-files", "/src/main.py", "1")
    _seed(client, "agent-files", "/src/util/helper.py", "2")
    _seed(client, "agent-files", "/readme.md", "3")
    infos = backend.glob_info("**/*.py", "/")
    paths = {i["path"] for i in infos}
    assert paths == {"/src/main.py", "/src/util/helper.py"}


# --------------------------------------------------------------------------- #
# namespace / prefix 隔离
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_prefix_isolation(client):
    # 两个不同 namespace 共享同一个 client，但互不可见
    a = MinIOBackend(bucket_name="munchkin-private", prefix="ns-a", client=client)
    b = MinIOBackend(bucket_name="munchkin-private", prefix="ns-b", client=client)
    a.write("/shared.txt", "from-a")
    # b 看不到 a 的文件
    assert b.read("/shared.txt").error is not None
    assert [e["path"] for e in b.ls_info("/")] == []
    # a 能读到自己的文件
    assert a.read("/shared.txt").file_data["content"] == "from-a"
    # key 命名空间正确
    assert "ns-a/shared.txt" in client.store
    assert "ns-b/shared.txt" not in client.store


@pytest.mark.unit
def test_other_namespace_objects_not_listed(client):
    client.store["ns-other/secret.txt"] = b"top secret"
    backend = MinIOBackend(bucket_name="munchkin-private", prefix="agent-files", client=client)
    assert backend.ls_info("/") == []
    assert backend.grep_raw("secret") == []
    assert backend.read("/secret.txt").error is not None


@pytest.mark.unit
def test_empty_prefix_uses_root_keys(client):
    backend = MinIOBackend(bucket_name="munchkin-private", prefix="", client=client)
    backend.write("/top.txt", "data")
    assert "top.txt" in client.store
    assert backend.read("/top.txt").file_data["content"] == "data"


# --------------------------------------------------------------------------- #
# download_files / upload_files（SkillsMiddleware 依赖）
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_download_files_returns_raw_bytes(backend, client):
    _seed(client, "agent-files", "/skills/markitdown/SKILL.md", "---\nname: markitdown\n---\nbody")
    [resp] = backend.download_files(["/skills/markitdown/SKILL.md"])
    assert resp.error is None
    assert resp.path == "/skills/markitdown/SKILL.md"
    assert resp.content == b"---\nname: markitdown\n---\nbody"


@pytest.mark.unit
def test_download_files_missing_returns_file_not_found(backend):
    from deepagents.backends.protocol import FILE_NOT_FOUND

    [resp] = backend.download_files(["/skills/nope/SKILL.md"])
    assert resp.content is None
    assert resp.error == FILE_NOT_FOUND


@pytest.mark.unit
def test_download_files_batch_preserves_order_and_partial(backend, client):
    _seed(client, "agent-files", "/a.txt", "AAA")
    resps = backend.download_files(["/a.txt", "/missing.txt"])
    assert [r.path for r in resps] == ["/a.txt", "/missing.txt"]
    assert resps[0].content == b"AAA" and resps[0].error is None
    assert resps[1].content is None and resps[1].error is not None


@pytest.mark.unit
def test_upload_files_writes_namespaced_keys(backend, client):
    resps = backend.upload_files([("/skills/x/SKILL.md", b"hello"), ("/data/y.bin", b"\x00\x01")])
    assert all(r.error is None for r in resps)
    assert client.store["agent-files/skills/x/SKILL.md"] == b"hello"
    assert client.store["agent-files/data/y.bin"] == b"\x00\x01"


@pytest.mark.unit
def test_put_object_receives_stream_and_length(client):
    captured = {}

    class _SpyClient(FakeMinioClient):
        def put_object(self, bucket_name, object_name, data, length=-1, **kwargs):
            captured["is_stream"] = isinstance(data, BytesIO)
            captured["length"] = length
            return super().put_object(bucket_name, object_name, data, length=length, **kwargs)

    backend = MinIOBackend(bucket_name="munchkin-private", prefix="p", client=_SpyClient())
    backend.write("/f.txt", "hello")
    assert captured["is_stream"] is True
    assert captured["length"] == len(b"hello")
