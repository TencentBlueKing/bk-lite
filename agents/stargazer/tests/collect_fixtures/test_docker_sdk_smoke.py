# -*- coding: utf-8 -*-
"""docker SDK 可用性 smoke test。

背景:2026-07-07 发现 pyproject.toml 的 dependencies 里没声明 docker SDK,
导致 test_cli.py / test_docker_lifecycle.py / test_run_collector.py 在收集阶段
就 ModuleNotFoundError,Gap-1 真实采集对象完全跑不起来。本测试守护
"docker SDK 已声明并可导入"这条契约。
"""
from __future__ import annotations

import pytest


def test_docker_sdk_is_importable():
    """docker SDK 必须在项目 dependencies 中(否则 cli/docker_lifecycle/run_collector 单测全 collect 失败)。"""
    import docker  # noqa: F401
    assert hasattr(docker, "from_env"), "docker SDK 缺少 from_env()"


def test_docker_errors_is_importable():
    """docker.errors 子模块必须可用(docker_lifecycle 用 docker.errors.NotFound 捕获异常)。"""
    import docker.errors  # noqa: F401
    assert hasattr(docker.errors, "NotFound"), "docker.errors 缺少 NotFound"


def test_docker_lifecycle_module_loads_without_error():
    """docker_lifecycle.py 必须能完整 import(load 不报错=SDK API surface 与代码兼容)。"""
    from tests.collect_fixtures import docker_lifecycle  # noqa: F401