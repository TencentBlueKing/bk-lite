"""SSH 密钥文件读取的 service 层测试（B1）

验证抽取的 :func:`ExecutionTaskBaseService._read_ssh_key_file`：

- 使用 ``with`` 上下文管理器，异常路径不泄漏文件句柄；
- 精确捕获 ``FileNotFoundError`` / ``OSError``，不再吞掉非预期异常；
- 字节内容自动 ``decode("utf-8")``。
"""

from types import SimpleNamespace

import pytest

from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService


class _FakeFieldFile:
    """模拟 Target.ssh_key_file（FieldFile）：

    - ``__bool__``：依据 ``raise_on_open`` 设计简单地视作 truthy；
    - ``open(mode)``：返回支持上下文管理协议的文件句柄；
    - ``close_called``：用于断言句柄在异常路径也被关闭。
    """

    def __init__(self, content=b"PRIVATE-KEY", raise_on_open=None):
        self._content = content
        self._raise_on_open = raise_on_open
        self.close_called = False

    def __bool__(self):
        return True

    def open(self, mode="r"):
        if self._raise_on_open is not None:
            raise self._raise_on_open
        outer = self

        class _Handle:
            def read(self_inner):
                return outer._content

            def close(self_inner):
                outer.close_called = True

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                self_inner.close()
                return False

        return _Handle()


def _make_target(ssh_key_file, target_id=1):
    return SimpleNamespace(id=target_id, ssh_key_file=ssh_key_file)


@pytest.mark.unit
class TestReadSshKeyFile:
    def test_returns_none_when_no_key_file(self):
        target = _make_target(ssh_key_file=None)
        assert ExecutionTaskBaseService._read_ssh_key_file(target) is None

    def test_decodes_bytes_content(self):
        target = _make_target(_FakeFieldFile(content=b"line-bytes"))
        assert ExecutionTaskBaseService._read_ssh_key_file(target) == "line-bytes"

    def test_returns_string_content_as_is(self):
        target = _make_target(_FakeFieldFile(content="line-str"))
        assert ExecutionTaskBaseService._read_ssh_key_file(target) == "line-str"

    def test_closes_handle_via_context_manager(self):
        fake = _FakeFieldFile(content=b"k")
        target = _make_target(fake)
        ExecutionTaskBaseService._read_ssh_key_file(target)
        assert fake.close_called, "with 上下文应保证 close 被调用"

    def test_returns_none_on_file_not_found(self):
        target = _make_target(_FakeFieldFile(raise_on_open=FileNotFoundError("missing")))
        assert ExecutionTaskBaseService._read_ssh_key_file(target) is None

    def test_returns_none_on_os_error(self):
        target = _make_target(_FakeFieldFile(raise_on_open=OSError("permission denied")))
        assert ExecutionTaskBaseService._read_ssh_key_file(target) is None

    def test_non_file_io_exceptions_propagate(self):
        """非文件 IO 类异常不再被静默吞掉（旧实现 except Exception 会屏蔽问题）"""

        class _Boom(_FakeFieldFile):
            def open(self, mode="r"):
                raise RuntimeError("unexpected")

        target = _make_target(_Boom())
        with pytest.raises(RuntimeError):
            ExecutionTaskBaseService._read_ssh_key_file(target)


@pytest.mark.unit
@pytest.mark.django_db
class TestGetSshCredentialsUsesReadHelper:
    """get_ssh_credentials 复用 _read_ssh_key_file，避免重复读取逻辑。"""

    def test_get_ssh_credentials_delegates_to_read_helper(self, monkeypatch):
        from apps.job_mgmt.models import Target

        target = Target.objects.create(
            name="t1",
            ip="10.0.0.1",
            ssh_port=22,
            ssh_user="root",
        )
        monkeypatch.setattr(ExecutionTaskBaseService, "_read_ssh_key_file", staticmethod(lambda t: "PRIVATE"))
        creds = ExecutionTaskBaseService.get_ssh_credentials(target.id)
        assert creds["private_key"] == "PRIVATE"
        assert creds["host"] == "10.0.0.1"
        assert creds["username"] == "root"
        assert creds["port"] == 22

    def test_get_ssh_credentials_missing_target_returns_empty(self):
        assert ExecutionTaskBaseService.get_ssh_credentials(999_999) == {}
