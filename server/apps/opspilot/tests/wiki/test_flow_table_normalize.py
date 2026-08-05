"""Tests for numbered flowchart table normalization."""

from apps.opspilot.services.wiki.parsing.flow_table_normalize import normalize_numbered_flow_table, normalize_numbered_flow_tables_in_markdown
from apps.opspilot.services.wiki.parsing.fragmented_table import should_rasterize_pdf_page

_FLOW_ZIGZAG = "\n".join(
    [
        "",
        (
            "|                   |        | 2. 版本文件上传      |          |             "
            "| 4. 停止进程        |                | 6. 进程启动        |                "
            "| 8. 告警屏蔽解除       |"
        ),
        (
            "| ----------------- | ------ | -------------- | -------- | ----------- "
            "| -------------- | -------------- | -------------- | -------------- "
            "| --------------- |"
        ),
        (
            "|                   |        | 通过作业平台把版本文件上传到 |          |             "
            "| 上机用命令行或脚本将进程临时 |                | 上机用命令行或脚本将服务进程 |                "
            "| 确认OK后，登录监控系统将之前 |"
        ),
        (
            "|                   |        |                | 发布平台的中转机 |             "
            "| 停止，为更新做准备      |                | 重新拉起，使其恢复服务    |                "
            "| 的屏蔽策略解除，恢复防护！   |"
        ),
        (
            "| 1. 版本打包           |        |                |          | 3. 屏蔽告警     "
            "|                | 5. 更新版本        |                | 7. 测试检查        "
            "|                 |"
        ),
        (
            "| 开发从git或svn将文件打包并交 |        |                |          | 前往监控系统屏蔽对应的 "
            "|                | 通过作业平台把版本文件分发到 |                | 利用自动化测试工具或系统跑一 "
            "|                 |"
        ),
        (
            "|                   | 付给运维人员 |                |          |             "
            "| 业务告警策略。        | 各个对应的服务主机上     |                | 遍测试流程，验证可用性    "
            "|                 |"
        ),
        "",
    ]
)


def test_normalize_flow_zigzag_to_step_table():
    out = normalize_numbered_flow_table(_FLOW_ZIGZAG)
    assert out is not None
    assert "| 步骤 | 名称 | 说明 |" in out
    assert "| 1 | 版本打包 | 开发从git或svn将文件打包并交付给运维人员 |" in out
    assert "| 2 | 版本文件上传 | 通过作业平台把版本文件上传到发布平台的中转机 |" in out
    assert "| 3 | 屏蔽告警 | 前往监控系统屏蔽对应的业务告警策略。 |" in out
    assert "| 4 | 停止进程 | 上机用命令行或脚本将进程临时停止，为更新做准备 |" in out
    assert "| 5 | 更新版本 | 通过作业平台把版本文件分发到各个对应的服务主机上 |" in out
    assert "| 6 | 进程启动 | 上机用命令行或脚本将服务进程重新拉起，使其恢复服务 |" in out
    assert "| 7 | 测试检查 | 利用自动化测试工具或系统跑一遍测试流程，验证可用性 |" in out
    assert "| 8 | 告警屏蔽解除 | 确认OK后，登录监控系统将之前的屏蔽策略解除，恢复防护！ |" in out
    # After normalize, page should not need rasterize for this table alone
    page = "# 标准运维\n\n" + out
    assert should_rasterize_pdf_page(page) is False


def test_normalize_in_page_markdown():
    page = "利用标准运维跨系统编排能力\n\n" + _FLOW_ZIGZAG + "\n\n下文"
    out = normalize_numbered_flow_tables_in_markdown(page)
    assert "| 步骤 | 名称 | 说明 |" in out
    assert "1. 版本打包" not in out or "| 1 | 版本打包 |" in out
    assert "利用标准运维跨系统编排能力" in out
    assert "下文" in out


def test_normal_simple_table_unchanged():
    simple = """
| 组件 | 说明 | 功能 |
| --- | --- | --- |
| nginx | Web 服务器 | 反向代理 |
| mysql | 关系型数据库 | 持久化存储 |
"""
    assert normalize_numbered_flow_table(simple) is None
    assert normalize_numbered_flow_tables_in_markdown(simple) == simple
