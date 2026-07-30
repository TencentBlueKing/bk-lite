"""精简 SNMP 资产：剥离各插件复制的过滤 UI / Jinja / ifType OID。

上述契约由运行时单一真相源注入：
  apps.monitor.utils.snmp_interface_template

正常情况下 support-files/Telegraf/snmp 保持与上游一致，无需批量改插件文件。
本脚本仅用于清理误写入磁盘的重复块。

用法（仓库根目录）:
  python3 server/apps/monitor/management/scripts/patch_snmp_interface_filters_assets.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SNMP_DIR = ROOT / "server/apps/monitor/support-files/plugins/Telegraf/snmp"

FILTER_MARKER_BEGIN = "# ---- BK-Lite SNMP interface dimension filters (begin) ----"
FILTER_MARKER_END = "# ---- BK-Lite SNMP interface dimension filters (end) ----"

FILTER_FIELD_NAMES = {
    "iftype_exclude",
    "iftype_include",
    "ifdescr_exclude",
    "ifdescr_include",
}

INTERFACE_HINT_RE = re.compile(
    r'name\s*=\s*"ifDescr"|oid\s*=\s*"1\.3\.6\.1\.2\.1\.2\.2"|oid\s*=\s*"1\.3\.6\.1\.2\.1\.31\.1\.1"',
    re.MULTILINE,
)
FILTER_BLOCK_RE = re.compile(
    re.escape(FILTER_MARKER_BEGIN) + r".*?" + re.escape(FILTER_MARKER_END) + r"\n?",
    re.DOTALL,
)
TAGEXCLUDE_IFTYPE_RE = re.compile(r'^\s*tagexclude\s*=\s*\["ifType"\]\s*\n', re.MULTILINE)
CANONICAL_IFTYPE_FIELD_RE = re.compile(
    r"\n?[ \t]*\[\[inputs\.snmp\.table\.field\]\]\s*\n"
    r"[ \t]*oid\s*=\s*\"1\.3\.6\.1\.2\.1\.2\.2\.1\.3\"\s*\n"
    r"[ \t]*name\s*=\s*\"ifType\"\s*\n"
    r"[ \t]*is_tag\s*=\s*true\s*\n?",
    re.MULTILINE,
)


def _has_interface_collection(text: str) -> bool:
    return bool(INTERFACE_HINT_RE.search(text))


def _strip_runtime_injected_bits(text: str) -> str:
    text = FILTER_BLOCK_RE.sub("", text)
    text = TAGEXCLUDE_IFTYPE_RE.sub("", text)
    text = CANONICAL_IFTYPE_FIELD_RE.sub("\n", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def patch_template(path: Path) -> dict:
    original = path.read_text(encoding="utf-8")
    if not _has_interface_collection(original):
        return {"path": str(path), "skipped": "no-interface"}
    text = _strip_runtime_injected_bits(original)
    if text != original:
        path.write_text(text, encoding="utf-8")
    return {
        "path": str(path.relative_to(ROOT)),
        "changed": text != original,
    }


def patch_ui(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    tmpl_candidates = list(path.parent.glob("*.child.toml.j2"))
    if not tmpl_candidates:
        return {"path": str(path), "skipped": "no-template"}
    tmpl_text = tmpl_candidates[0].read_text(encoding="utf-8")
    if not _has_interface_collection(tmpl_text):
        return {"path": str(path), "skipped": "no-interface"}

    form_fields = data.get("form_fields") or []
    kept = [f for f in form_fields if not (isinstance(f, dict) and f.get("name") in FILTER_FIELD_NAMES)]
    changed = len(kept) != len(form_fields)
    if data.pop("advanced_panel", None) is not None:
        changed = True
    if changed:
        data["form_fields"] = kept
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path.relative_to(ROOT)), "changed": changed}


def main() -> int:
    if not SNMP_DIR.is_dir():
        print(f"SNMP dir not found: {SNMP_DIR}", file=sys.stderr)
        return 1

    tmpl_results = [patch_template(path) for path in sorted(SNMP_DIR.glob("*/*.child.toml.j2"))]
    ui_results = [patch_ui(path) for path in sorted(SNMP_DIR.glob("*/UI.json"))]

    tmpl_changed = sum(1 for r in tmpl_results if r.get("changed"))
    ui_changed = sum(1 for r in ui_results if r.get("changed"))
    print(f"templates changed={tmpl_changed}/{len(tmpl_results)}")
    print(f"ui changed={ui_changed}/{len(ui_results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
