"""Tests for product-architecture feature-map table normalization."""

from apps.opspilot.services.wiki.parsing.architecture_normalize import (
    normalize_architecture_feature_map,
    normalize_architecture_feature_maps_in_markdown,
)
from apps.opspilot.services.wiki.parsing.fragmented_table import should_rasterize_pdf_page

_NODE_ARCH = """
|                   | Agent管理 |         | 插件管理 |         |         |
| ----------------- | ------ | ------- | ---- | ------- | ------- |
| Agent状态管理         | Agent普通安装 | Agent批量安装 | 插件状态管理 | 插件安装维护 | 添加新插件包 |
| 云区域管理             |        |         |      |         |         |
| 云区域查看             |        |         |      |         | Proxy安装 |
| 云区域创建             |        |         |      |         |         |
| 任务历史              |        |         |      |         |         |
| 全局配置              |        |         |      |         |         |
| 查看历史任务            |        | 查看任务详情 |      |         |         |
|                   |        |         | GSE环境配置 |         | 任务配置 |
"""


def test_normalize_node_architecture_to_module_table():
    out = normalize_architecture_feature_map(_NODE_ARCH)
    assert out is not None
    assert "| 模块 | 功能 |" in out
    assert "| Agent管理 | Agent状态管理、Agent普通安装、Agent批量安装 |" in out
    assert "| 插件管理 | 插件状态管理、插件安装维护、添加新插件包 |" in out
    assert "| 云区域管理 | 云区域查看、Proxy安装、云区域创建 |" in out
    assert "| 任务历史 | 查看历史任务、查看任务详情 |" in out
    assert "| 全局配置 | GSE环境配置、任务配置 |" in out
    page = "# 节点管理产品架构\n\n" + out
    assert should_rasterize_pdf_page(page) is False


def test_normalize_in_page_keeps_surrounding_text():
    page = "节点管理产品架构\n\n" + _NODE_ARCH + "\n\n下文"
    out = normalize_architecture_feature_maps_in_markdown(page)
    assert "| 模块 | 功能 |" in out
    assert "节点管理产品架构" in out
    assert "下文" in out


def test_normal_data_table_unchanged():
    simple = """
| 组件 | 说明 | 功能 |
| --- | --- | --- |
| nginx | Web 服务器 | 反向代理 |
| mysql | 关系型数据库 | 持久化存储 |
"""
    assert normalize_architecture_feature_map(simple) is None
    assert normalize_architecture_feature_maps_in_markdown(simple) == simple


# Real MarkItDown output for 节点管理产品架构 (material 15 page 76):
# one slide shattered into 3 tables + module labels as plain text.
_NODE_ARCH_SPLIT = """
节点管理产品架构
|           | Agent管理   |           |        | 插件管理   |        |
| --------- | --------- | --------- | ------ | ------ | ------ |
| Agent状态管理 | Agent普通安装 | Agent批量安装 | 插件状态管理 | 插件安装维护 | 添加新插件包 |
云区域管理
| 云区域查看 |     |     |     |     | Proxy安装 |
| ----- | --- | --- | --- | --- | ------- |
云区域创建
任务历史
全局配置
| 查看历史任务 |     | 查看任务详情 |         |     |      |
| ------ | --- | ------ | ------- | --- | --- |
|                   |        |         | GSE环境配置 |         | 任务配置 |
"""


def test_normalize_split_architecture_page_from_markitdown():
    out = normalize_architecture_feature_maps_in_markdown(_NODE_ARCH_SPLIT)
    assert "| 模块 | 功能 |" in out
    assert "节点管理产品架构" in out
    assert "| Agent管理 | Agent状态管理、Agent普通安装、Agent批量安装 |" in out
    assert "| 插件管理 | 插件状态管理、插件安装维护、添加新插件包 |" in out
    assert "| 云区域管理 |" in out
    assert "云区域查看" in out and "Proxy安装" in out and "云区域创建" in out
    assert "| 任务历史 |" in out and "查看历史任务" in out
    assert "| 全局配置 |" in out and "GSE环境配置" in out
    assert "Agent状态管理 |" not in out  # old sparse header gone
    assert should_rasterize_pdf_page(out) is False
