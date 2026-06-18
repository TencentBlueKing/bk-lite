"""job_mgmt 配置常量解析的纯单测。

覆盖 :func:`apps.job_mgmt.config._int_env`：环境变量覆盖、非法值回退默认。
这些常量驱动 ExecutionTaskBaseService.MAX_WORKERS 与定时任务重试间隔，
解析出错会直接影响并发与调度，需锁定契约。
"""

import pytest

from apps.job_mgmt.config import _int_env


@pytest.mark.unit
class TestIntEnv:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("JOB_TEST_INT", raising=False)
        assert _int_env("JOB_TEST_INT", 10) == 10

    def test_env_override_parsed_as_int(self, monkeypatch):
        monkeypatch.setenv("JOB_TEST_INT", "25")
        assert _int_env("JOB_TEST_INT", 10) == 25

    def test_invalid_value_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("JOB_TEST_INT", "not-a-number")
        assert _int_env("JOB_TEST_INT", 7) == 7

    def test_empty_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("JOB_TEST_INT", "")
        assert _int_env("JOB_TEST_INT", 7) == 7

    def test_negative_value_passes_through(self, monkeypatch):
        """_int_env 不做下限约束，负值原样返回（运维配置职责）。"""
        monkeypatch.setenv("JOB_TEST_INT", "-3")
        assert _int_env("JOB_TEST_INT", 10) == -3
