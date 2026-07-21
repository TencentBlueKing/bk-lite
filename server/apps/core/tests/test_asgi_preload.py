"""ASGI worker 启动时的语言缓存预热回归测试。"""

import runpy
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_asgi_worker_preloads_monitor_language_cache(monkeypatch):
    """插件翻译扫描在 worker 启动完成，不能落在首个监控 API 请求上。"""
    from django.core import asgi as django_asgi
    from apps.core.utils import loader as loader_mod

    calls = []
    monkeypatch.setattr(django_asgi, "get_asgi_application", lambda: object())
    monkeypatch.setattr(loader_mod, "preload_language_cache", lambda **kwargs: calls.append(kwargs))

    asgi_path = Path(__file__).resolve().parents[3] / "asgi.py"
    runpy.run_path(str(asgi_path))

    assert calls == [{"apps": ["monitor"]}]
