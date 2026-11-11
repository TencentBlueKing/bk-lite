"""轻量镜像在正式 Python / Shell / 技能执行入口上的行为验证。"""

import io
import json
import os
import zipfile
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from apps.opspilot.metis.llm.middleware.python_sandbox import PythonSandboxMiddleware
from apps.opspilot.metis.llm.tools.python.executor import python_execute_direct
from apps.opspilot.metis.llm.tools.shell.shell_tools import shell_execute
from apps.opspilot.services.python_sandbox.runtime import PythonSandbox
from apps.opspilot.services.python_sandbox.skill_backend import ContainerSkillBackend

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not os.getenv("OPSPILOT_TEST_DOCKER"), reason="requires sandbox image and Docker")]


@pytest.fixture
def sandbox():
    runtime = PythonSandbox()
    try:
        yield runtime
    finally:
        runtime.close()


def test_offloaded_json_becomes_chinese_html_pdf_and_zip(sandbox):
    config = {"configurable": {"python_sandbox": sandbox}}
    payload = json.dumps({"items": [{"status": "active", "value": 2}, {"status": "closed", "value": 7}] * 200})
    message = ToolMessage(content=payload, tool_call_id="alerts")
    offloaded = PythonSandboxMiddleware(sandbox).wrap_tool_call(SimpleNamespace(tool_call={"name": "alerts"}), lambda _: message)
    assert "工具完整结果已保存" in offloaded.content
    code = f"""
from pathlib import Path
import ijson
from jinja2 import Environment
from markdown_it import MarkdownIt
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

with open({sandbox.files()[0]!r}, 'rb') as stream:
    total = sum(row['value'] for row in ijson.items(stream, 'items.item') if row['status'] == 'active')
env = Environment(autoescape=True)
body = MarkdownIt('commonmark', {{'html': False}}).render('# 告警汇总\\n合计：' + str(total))
html = env.from_string('<html><meta charset="utf-8"><title>{{{{ title }}}}</title>{{{{ body|safe }}}}</html>').render(
    title='<告警>', body=body)
Path('/workspace/report.html').write_text(html, encoding='utf-8')
pdfmetrics.registerFont(TTFont('WQY', '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'))
canvas = Canvas('/workspace/report.pdf')
canvas.setFont('WQY', 14)
canvas.drawString(50, 750, '告警汇总：' + str(total))
canvas.save()
print(total)
"""
    assert python_execute_direct.invoke({"code": code}, config=config) == "400"
    html = sandbox.read_workspace_file("/workspace/report.html").decode()
    assert "&lt;告警&gt;" in html and "<h1>告警汇总</h1>" in html and "合计：400" in html
    result = ContainerSkillBackend(sandbox).execute(
        "zip -q report.zip report.html report.pdf && unzip -q report.zip -d unpacked && file --mime-type unpacked/report.pdf"
    )
    assert result.exit_code == 0, result.output
    assert "application/pdf" in result.output
    assert sandbox.read_workspace_file("/workspace/unpacked/report.html").decode() == html
    assert sandbox.read_workspace_file("/workspace/unpacked/report.pdf") == sandbox.read_workspace_file("/workspace/report.pdf")
    extracted = shell_execute.invoke({"commands": ["pdftotext /workspace/unpacked/report.pdf -"]}, config=config)
    assert "告警汇总：400" in extracted
    assert "WenQuanYi" in shell_execute.invoke({"commands": ["pdffonts /workspace/report.pdf"]}, config=config)


def test_installed_dependencies_are_shared_by_shell_python_and_skills(sandbox):
    # Local packages exercise real installers without a package registry dependency.
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("opspilot_dep_probe.py", 'VALUE = "python-installed"\ndef main():\n    print(VALUE)\n')
        archive.writestr("opspilot_dep_probe-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: opspilot-dep-probe\nVersion: 1.0\n")
        archive.writestr("opspilot_dep_probe-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr("opspilot_dep_probe-1.0.dist-info/entry_points.txt", "[console_scripts]\nopspilot-python-probe = opspilot_dep_probe:main\n")
        archive.writestr("opspilot_dep_probe-1.0.dist-info/RECORD", "")
    sandbox.write_workspace_file("/workspace/opspilot_dep_probe-1.0-py3-none-any.whl", wheel.getvalue())
    sandbox.write_workspace_file(
        "/workspace/node-probe/package.json",
        json.dumps({"name": "opspilot-node-probe", "version": "1.0.0", "bin": {"opspilot-node-probe": "cli.js"}}).encode(),
    )
    sandbox.write_workspace_file("/workspace/node-probe/cli.js", b'#!/usr/bin/env node\nconsole.log("node-installed");\n')
    config = {"configurable": {"python_sandbox": sandbox}}
    installed = shell_execute.invoke(
        {
            "commands": [
                "python -m pip install --user --no-index /workspace/opspilot_dep_probe-1.0-py3-none-any.whl "
                "&& npm install -g /workspace/node-probe --offline"
            ]
        },
        config=config,
    )
    assert "Exit code:" not in installed, installed
    assert python_execute_direct.invoke({"code": "import opspilot_dep_probe; print(opspilot_dep_probe.VALUE)"}, config=config) == "python-installed"
    result = ContainerSkillBackend(sandbox).execute("opspilot-python-probe && opspilot-node-probe")
    assert result.exit_code == 0, result.output
    assert result.output == "python-installed\nnode-installed"
    assert shell_execute.invoke({"commands": ["opspilot-node-probe"]}, config=config) == "node-installed"
    other = PythonSandbox()
    try:
        assert "ModuleNotFoundError" in other.execute("import opspilot_dep_probe")
        assert other.execute_command("opspilot-node-probe").exit_code != 0
    finally:
        other.close()


def test_large_json_is_analyzed_with_bounded_process_memory(sandbox):
    config = {"configurable": {"python_sandbox": sandbox}}
    generated = python_execute_direct.invoke(
        {
            "code": """
import json
record = json.dumps({'value': 2, 'detail': 'x' * 1024})
with open('/workspace/large.json', 'w') as stream:
    stream.write('[')
    for i in range(50000):
        if i:
            stream.write(',')
        stream.write(record)
    stream.write(']')
print('ready')
"""
        },
        config=config,
    )
    assert generated == "ready"
    result = python_execute_direct.invoke(
        {
            "code": """
import ijson, json, os, resource
with open('/workspace/large.json', 'rb') as stream:
    total = sum(row['value'] for row in ijson.items(stream, 'item'))
print(json.dumps({'total': total, 'peak_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 'bytes': os.path.getsize('/workspace/large.json')}))
"""
        },
        config=config,
    )
    measured = json.loads(result)
    assert measured["total"] == 100000
    assert measured["bytes"] > 50 * 1024 * 1024
    assert measured["peak_kib"] < 128 * 1024, measured
    removed = ContainerSkillBackend(sandbox).execute("rm /workspace/large.json")
    assert removed.exit_code == 0
