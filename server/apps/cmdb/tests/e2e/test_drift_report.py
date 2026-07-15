"""字段漂移报告测试 —— 扫描 fixtures/<model_id>/04_expected_cmdb_result.json 跟
apps.cmdb.models.<Model> 反射字段定义比对,输出 model_id / missing_fields / extra_fields / type_mismatch 表格。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

E2E_ROOT = Path(__file__).parent
# 优先用 pytest 当前进程的 python(sys.executable),避免 macOS 上 'python' 不存在的问题
PYTHON_BIN = sys.executable


def test_drift_report_runs():
    """drift_report 跑通,返回 0 退出码,stdout 是 JSON 报告。"""
    report = subprocess.run(
        [PYTHON_BIN, "-m", "apps.cmdb.tests.e2e.utils.drift_report"],
        cwd=E2E_ROOT,
        capture_output=True,
        text=True,
    )
    assert report.returncode == 0, f"drift_report 失败: {report.stderr}"
    summary = json.loads(report.stdout)
    assert "results" in summary
    assert isinstance(summary["results"], list)


def test_drift_report_writes_markdown():
    """drift_report 必须生成 markdown 报告文件。"""
    md_path = E2E_ROOT / "drift_report.md"
    if md_path.exists():
        md_path.unlink()  # 先删,确保重新生成
    result = subprocess.run(
        [PYTHON_BIN, "-m", "apps.cmdb.tests.e2e.utils.drift_report", "--format", "markdown", "--output", str(md_path)],
        cwd=E2E_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"drift_report 失败: {result.stderr}"
    assert md_path.exists()
    content = md_path.read_text()
    assert "# 字段漂移报告" in content
    assert "model_id" in content
