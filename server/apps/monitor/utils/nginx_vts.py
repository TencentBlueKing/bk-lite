"""Nginx 虚拟主机流量（inputs.nginx_vts）在编辑表单与 Telegraf 配置之间的投影。

表单把开关和 URL 放在 child.content.config 上，方便和 stub_status 的 URL 分开。
Telegraf 的 inputs.nginx 不认识这两个字段；写回时必须挪到独立的
[[inputs.nginx_vts]]，否则 Telegraf 会拒载整份子配置，stub_status 一并停采。

未传开关时保持文档原样，避免旧客户端保存时清掉已开启的 VTS。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_FORM_KEYS = ("nginx_vts", "nginx_vts_url")


def _is_nginx_child(content: dict) -> bool:
    plugin = content.get("plugin")
    if isinstance(plugin, (list, tuple)) and len(plugin) >= 2 and tuple(plugin[:2]) == ("inputs", "nginx"):
        return True
    config = content.get("config")
    tags = config.get("tags") if isinstance(config, dict) else None
    if isinstance(tags, dict) and tags.get("config_type") == "nginx":
        return True
    document = content.get("_toml_document")
    inputs = document.get("inputs") if isinstance(document, dict) else None
    return isinstance(inputs, dict) and isinstance(inputs.get("nginx"), list)


def _enabled(value: Any) -> bool:
    return value in (True, 1, "1", "true", "True")


def _interval(config: dict) -> str:
    raw = config.get("interval")
    if raw in (None, ""):
        return "60s"
    text = str(raw).strip()
    if text.isdigit():
        return f"{text}s"
    return text


def _vts_urls(block: dict) -> list:
    urls = block.get("urls")
    if isinstance(urls, list):
        return [str(item) for item in urls if str(item or "").strip()]
    if isinstance(urls, str) and urls.strip():
        return [urls.strip()]
    return []


def expose_nginx_vts_for_edit(content: dict | None) -> dict | None:
    """把 [[inputs.nginx_vts]] 投影到 content.config，供接入页回显。"""
    if not isinstance(content, dict) or not _is_nginx_child(content):
        return content
    config = content.get("config")
    if not isinstance(config, dict):
        return content
    document = content.get("_toml_document")
    inputs = document.get("inputs") if isinstance(document, dict) else None
    blocks = inputs.get("nginx_vts") if isinstance(inputs, dict) else None
    projected = deepcopy(config)
    if isinstance(blocks, list) and blocks and isinstance(blocks[0], dict):
        urls = _vts_urls(blocks[0])
        projected["nginx_vts"] = True
        projected["nginx_vts_url"] = urls[0] if urls else ""
    else:
        projected["nginx_vts"] = False
        projected.pop("nginx_vts_url", None)
    content["config"] = projected
    return content


def _ensure_document(content: dict, config: dict) -> dict:
    document = content.get("_toml_document")
    if isinstance(document, dict):
        return document
    plugin = content.get("plugin") or ("inputs", "nginx")
    key1, key2 = tuple(plugin[:2])
    document = {key1: {key2: [deepcopy(config)]}}
    content["_toml_document"] = document
    return document


def sync_nginx_vts_on_writeback(content: dict | None) -> dict | None:
    """把表单上的 VTS 开关和 URL 写到 inputs.nginx_vts，并从 inputs.nginx 删除。"""
    if not isinstance(content, dict) or not _is_nginx_child(content):
        return content
    config = content.get("config")
    if not isinstance(config, dict):
        return content
    if not any(key in config for key in _FORM_KEYS):
        return content

    enabled = _enabled(config.pop("nginx_vts", False))
    url = str(config.pop("nginx_vts_url", "") or "").strip()
    document = _ensure_document(content, config)
    inputs = document.setdefault("inputs", {})
    if not isinstance(inputs, dict):
        return content

    if not enabled or not url:
        inputs.pop("nginx_vts", None)
        return content

    tags = config.get("tags") if isinstance(config.get("tags"), dict) else {}
    inputs["nginx_vts"] = [
        {
            "startup_error_behavior": config.get("startup_error_behavior") or "retry",
            "urls": [url],
            "interval": _interval(config),
            "tags": deepcopy(tags),
        }
    ]
    return content
