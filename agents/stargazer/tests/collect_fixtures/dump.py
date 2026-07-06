# -*- coding: utf-8 -*-
"""
落盘模块 — 把采集到的 raw_stdout 写入 fixtures/collect/<model>.json。

设计原则：
- 原子写：先写临时文件 + fsync，再 rename，避免半成品。
- 敏感字段掩码：password / secret / token 等字段落盘前替换为 "***"。
- schema 固定：下游 e2e 测试依赖字段名，不要随便改名。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SENSITIVE_KEY_PATTERN = re.compile(r"(password|secret|token|passwd)", re.IGNORECASE)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "collect"


def mask_sensitive(value: Any) -> Any:
    """递归把 dict/list 中所有"敏感 key"的值替换为 "***"。"""
    if isinstance(value, dict):
        return {
            k: ("***" if SENSITIVE_KEY_PATTERN.search(k) else mask_sensitive(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    return value


def dump(
    model_id: str,
    raw_stdout: Any,
    container_meta: Dict[str, Any],
    params: Dict[str, Any],
    out_dir: Optional[Path] = None,
) -> Path:
    """把采集结果原子写入 <out_dir>/<model_id>.json。"""
    if out_dir is None:
        out_dir = FIXTURES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "model_id": model_id,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "image": container_meta.get("image", ""),
        "container_meta": container_meta,
        "params": mask_sensitive(params),
        "raw_stdout": raw_stdout,
    }

    target = out_dir / f"{model_id}.json"
    tmp = target.with_suffix(".json.tmp")

    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception:
        # 清理半成品文件
        if tmp.exists():
            tmp.unlink()
        raise

    return target