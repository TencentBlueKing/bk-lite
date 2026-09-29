"""AGUI 整轮 SSE 墙钟死线：默认关闭，仅显式正数启用。"""

import os

import pytest

from apps.opspilot.metis.llm.chain.graph import agui_run_deadline_seconds

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_deadline_env(monkeypatch):
    monkeypatch.delenv("AGUI_RUN_DEADLINE_SECONDS", raising=False)
    monkeypatch.delenv("LLM_INVOKE_TIMEOUT", raising=False)


def test_agui_run_deadline_defaults_to_none():
    assert agui_run_deadline_seconds() is None


@pytest.mark.parametrize("value", ["0", "off", "none", "false", "disabled", " OFF "])
def test_agui_run_deadline_explicit_off(monkeypatch, value):
    monkeypatch.setenv("AGUI_RUN_DEADLINE_SECONDS", value)
    assert agui_run_deadline_seconds() is None


def test_agui_run_deadline_explicit_positive(monkeypatch):
    monkeypatch.setenv("AGUI_RUN_DEADLINE_SECONDS", "120")
    assert agui_run_deadline_seconds() == 120.0


def test_agui_run_deadline_floors_at_30(monkeypatch):
    monkeypatch.setenv("AGUI_RUN_DEADLINE_SECONDS", "10")
    assert agui_run_deadline_seconds() == 30.0


def test_agui_run_deadline_invalid_is_none(monkeypatch):
    monkeypatch.setenv("AGUI_RUN_DEADLINE_SECONDS", "not-a-number")
    assert agui_run_deadline_seconds() is None


def test_agui_run_deadline_no_longer_derives_from_llm_timeout(monkeypatch):
    monkeypatch.setenv("LLM_INVOKE_TIMEOUT", "300")
    assert os.getenv("AGUI_RUN_DEADLINE_SECONDS") is None
    assert agui_run_deadline_seconds() is None
