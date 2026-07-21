"""字段漂移报告工具 —— 扫描 fixtures/<model_id>/04_expected_cmdb_result.json 跟
apps.cmdb.models.<Model> 反射字段定义比对,生成 JSON / Markdown 报告。

用法:
  python -m apps.cmdb.tests.e2e.utils.drift_report                    # stdout JSON
  python -m apps.cmdb.tests.e2e.utils.drift_report --format markdown  # stdout Markdown
  python -m apps.cmdb.tests.e2e.utils.drift_report -o drift_report.md # 写文件
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def

E2E_ROOT = Path(__file__).parents[1]  # apps/cmdb/tests/e2e
FIXTURES_DIR = E2E_ROOT / "fixtures"

# 系统级字段,不属于 plugin 业务字段,比对时排除
SYSTEM_FIELDS = {
    "inst_name",
    "model_id",
    "id",
    "create_time",
    "update_time",
    "assos",
    "_placeholder_reason",
    "license_status",
}


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _type_match(value: Any, expected_type: str) -> bool:
    if expected_type == "int":
        return isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    if expected_type == "str":
        return isinstance(value, str)
    if expected_type == "float":
        return isinstance(value, (int, float))
    if expected_type == "bool":
        return isinstance(value, bool)
    return True


def _compare(model_id: str) -> dict[str, Any]:
    """比对单个 model_id 的 04 expected 跟 model 字段定义。"""
    try:
        model_fields = get_model_field_def(model_id)
    except KeyError as e:
        return {
            "model_id": model_id,
            "status": "no_schema",
            "missing_fields": [],
            "extra_fields": [],
            "type_mismatch": [],
            "note": str(e),
        }
    model_field_names = set(model_fields.keys())

    expected = _read_json(FIXTURES_DIR / model_id / "04_expected_cmdb_result.json")
    if not expected:
        return {
            "model_id": model_id,
            "status": "no_fixture",
            "missing_fields": [],
            "extra_fields": [],
            "type_mismatch": [],
        }

    # 支持 expected_instance_subset(主流) 和 expected_instance(host 风格)
    expected_subset = expected.get("expected_instance_subset") or expected.get("expected_instance") or {}
    if not expected_subset:
        return {
            "model_id": model_id,
            "status": "no_expected_subset",
            "missing_fields": [],
            "extra_fields": [],
            "type_mismatch": [],
        }

    expected_field_names = set(expected_subset.keys())

    # 缺字段:model 有但 expected 没有(排除系统字段)
    missing = (model_field_names - expected_field_names) - SYSTEM_FIELDS

    # 多字段:expected 有但 model 没有
    extra = expected_field_names - model_field_names - SYSTEM_FIELDS

    # 类型不匹配
    type_mismatch = []
    for field_name, expected_value in expected_subset.items():
        if field_name not in model_fields:
            continue
        if expected_value is None or expected_value == "":
            continue  # 空值不做类型比对
        model_def = model_fields[field_name]
        if not _type_match(expected_value, model_def.field_type):
            type_mismatch.append({
                "field": field_name,
                "expected_type": type(expected_value).__name__,
                "model_type": model_def.field_type,
            })

    status = "ok"
    if missing or type_mismatch:
        status = "missing_or_mismatch"
    if extra:
        status = "extra_fields"

    return {
        "model_id": model_id,
        "status": status,
        "missing_fields": sorted(missing),
        "extra_fields": sorted(extra),
        "type_mismatch": type_mismatch,
    }


def _to_markdown(results: list[dict]) -> str:
    lines = ["# 字段漂移报告", ""]
    lines.append(f"扫描 {len(results)} 个 model_id")
    lines.append("")

    by_status: dict[str, list] = {
        "ok": [],
        "missing_or_mismatch": [],
        "extra_fields": [],
        "no_fixture": [],
        "no_expected_subset": [],
        "no_schema": [],
    }
    for r in results:
        by_status.setdefault(r["status"], []).append(r)

    lines.append("## 统计")
    lines.append(f"- ok(完全对齐): {len(by_status['ok'])}")
    lines.append(f"- 缺字段或类型错: {len(by_status['missing_or_mismatch'])}")
    lines.append(f"- 多字段: {len(by_status['extra_fields'])}")
    lines.append(f"- 无 fixture: {len(by_status['no_fixture'])}")
    lines.append(f"- 无 expected_subset: {len(by_status['no_expected_subset'])}")
    lines.append(f"- 无 schema: {len(by_status['no_schema'])}")
    lines.append("")

    if by_status["missing_or_mismatch"]:
        lines.append("## 缺字段 / 类型错")
        lines.append("")
        lines.append("| model_id | 缺字段 | 类型错 |")
        lines.append("| --- | --- | --- |")
        for r in by_status["missing_or_mismatch"]:
            missing = ", ".join(r["missing_fields"][:5]) + ("..." if len(r["missing_fields"]) > 5 else "")
            tm = ", ".join(f"{tm['field']}({tm['expected_type']}→{tm['model_type']})" for tm in r["type_mismatch"][:5])
            lines.append(f"| {r['model_id']} | {missing} | {tm} |")
        lines.append("")

    if by_status["extra_fields"]:
        lines.append("## 多字段(expected 有但 model 没有)")
        lines.append("")
        lines.append("| model_id | 多字段 |")
        lines.append("| --- | --- |")
        for r in by_status["extra_fields"]:
            extra = ", ".join(r["extra_fields"][:5])
            lines.append(f"| {r['model_id']} | {extra} |")
        lines.append("")

    if by_status["ok"]:
        lines.append("## 完全对齐")
        lines.append("")
        ok_ids = sorted(r["model_id"] for r in by_status["ok"])
        # 50 个一行,避免单行过长
        for i in range(0, len(ok_ids), 8):
            lines.append("- " + ", ".join(ok_ids[i:i + 8]))
        lines.append("")

    if by_status["no_fixture"]:
        lines.append("## 无 fixture 04_expected_cmdb_result.json")
        lines.append("")
        for r in by_status["no_fixture"]:
            lines.append(f"- {r['model_id']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="CMDB 字段漂移报告工具")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", "-o", help="输出文件路径(默认 stdout)")
    args = parser.parse_args()

    # 扫描 fixtures 目录所有 model_id
    model_ids = sorted([d.name for d in FIXTURES_DIR.iterdir() if d.is_dir()])
    results = [_compare(mid) for mid in model_ids]

    if args.format == "json":
        output = json.dumps({"results": results}, ensure_ascii=False, indent=2)
    else:
        output = _to_markdown(results)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"报告写入 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
