"""监控插件指引文档读取服务。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.models import MonitorPlugin

SUPPORTED_GUIDE_LOCALES = ("zh-Hans", "en")


class PluginGuideService:
    """从插件目录读取 Markdown 指引内容。"""

    @staticmethod
    def normalize_locale(locale: Optional[str]) -> str:
        raw = (locale or "zh-Hans").strip()
        lowered = raw.lower().replace("_", "-")
        if lowered.startswith("en"):
            return "en"
        if lowered.startswith("zh"):
            return "zh-Hans"
        return "zh-Hans"

    @staticmethod
    def resolve_plugin_dir(plugin: MonitorPlugin) -> Optional[Path]:
        collector = (plugin.collector or "").strip()
        collect_type = (plugin.collect_type or "").strip()
        plugin_name = (plugin.name or "").strip()
        if not collector or not collect_type or not plugin_name:
            return None

        for root in (PluginConstants.DIRECTORY, PluginConstants.ENTERPRISE_DIRECTORY):
            base = Path(root) / collector / collect_type
            if not base.is_dir():
                continue
            matched_by_name: Optional[Path] = None
            for child in sorted(base.iterdir()):
                if not child.is_dir():
                    continue
                metrics_file = child / "metrics.json"
                if metrics_file.is_file():
                    try:
                        data = json.loads(metrics_file.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        data = {}
                    if data.get("plugin") == plugin_name:
                        return child
                if child.name.lower() == plugin_name.lower():
                    matched_by_name = child
            if matched_by_name is not None:
                return matched_by_name
        return None

    @classmethod
    def get_guide(cls, plugin: MonitorPlugin, locale: Optional[str] = None) -> Dict[str, Any]:
        preferred_locale = cls.normalize_locale(locale)
        # name 优先用 UI.json / metrics.json 的 object_name，回退到 plugin.name。
        # 同一插件可能有多个采集类型 / 多个实例，必须稳定且可读。
        name = (getattr(plugin, "name", "") or "").strip()
        plugin_dir = cls.resolve_plugin_dir(plugin)
        if plugin_dir is not None:
            for meta_file in ("UI.json", "metrics.json"):
                meta_path = plugin_dir / meta_file
                if not meta_path.is_file():
                    continue
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                meta_name = (data.get("object_name") or data.get("name") or "").strip()
                if meta_name:
                    name = meta_name
                    break
        if plugin_dir is None:
            return {
                "has_guide": False,
                "content": "",
                "locale": preferred_locale,
                "source": None,
                "name": name,
            }

        candidates = [
            (f"guide/{preferred_locale}.md", plugin_dir / "guide" / f"{preferred_locale}.md"),
        ]
        # README 的语言无法可靠判定。中文环境可继续以 README 作为历史兼容回退；
        # 英文环境宁可隐藏没有英文 guide 的入口，也不能把中文 README 伪装成英文指引。
        if preferred_locale == "zh-Hans":
            candidates.append(("README.md", plugin_dir / "README.md"))
        for source, path in candidates:
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not content:
                continue
            return {
                "has_guide": True,
                "content": content,
                "locale": preferred_locale,
                "source": source,
                "name": name,
            }

        return {
            "has_guide": False,
            "content": "",
            "locale": preferred_locale,
            "source": None,
            "name": name,
        }
