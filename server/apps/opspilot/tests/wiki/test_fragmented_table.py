"""Unit tests for fragmented markdown table heuristics."""

from apps.opspilot.services.wiki.parsing.fragmented_table import (
    is_fragmented_prose_markdown,
    is_fragmented_table,
    is_fragmented_table_markdown,
    salvage_sparse_layout_table,
    should_rasterize_pdf_page,
)

# Sample from real MarkItDown PDF output (layout brochure).
_FRAGMENTED_CMD_B = """
| ······ 负 | 网 防 存 | 机 主 | 基   |       |     |     |
| -------- | ----- | --- | --- | ----- | --- | --- |
| 载        | 络 火 储 | 房 机 | 础   | 自定义属性 | 发   | 变   |
| 均        | 设 墙   |     |     |       |     |     |
|          |       |     |     |       | 布   | 更   |
设
| 衡   | 备   |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- |
| 业   | 容 自 进 | 业 业 |     |     | 故   |     |
| --- | --- | --- | --- | --- | --- | --- |
| 务   | 器 定 程 | 务 务 | 业   |     | 维   |     |
| --- | --- | --- | --- | --- | --- | --- |
|     |       |     |     |      | 障   | 器   |
| --- | --- | --- | --- | ---- | --- | --- |
| 配   | 配 义 端 | 拓 信 |     | 动态分组 |     |     |
"""

_FRAGMENTED_BACKEND = """
|     |     |     |     |     |     | 台 登 | 权   | 安   |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|     |     |     |     |     |     | 录   | 日 限   | 云 全  | 云API 后台任务 | 调度引擎 |
| --- | --- | --- | --- | --- | --- | --- | ----- | ---- | --------- | ---- |
|     |     |     |     |     |     |     | 志 API | 用    | 调用示例 示例   | 示例   |
|     |     |     |     | 监控  | 代码  | 鉴   | 控     | 防    |           |      |
|     | 监控  | 代码  |     |     |     |     |       | TAGS |           |      |
|     |     |     |     |     |     | 权   | 制     | 护    |           |      |
|     | 告警  | 部署  |     | 告警  | 部署  |     |       |      |           |      |
"""

_NORMAL_ORG = """
| IEG     | WXG   | TEG     | PCG      | CSIG      | CDG     |
| ------- | ----- | ------- | -------- | --------- | ------- |
| 互动娱乐事业群 | 微信事业群 | 技术工程事业群 | 平台与内容事业群 | 云与智慧产业事业群 | 企业发展事业群 |
| 腾讯游戏    |       | 腾讯大数据   | QQ       | 腾讯云       | 腾讯广告    |
"""

_NORMAL_SIMPLE = """
| 组件 | 说明 | 功能 |
| --- | --- | --- |
| nginx | Web 服务器 | 反向代理 |
| mysql | 关系型数据库 | 持久化存储 |
| redis | 内存数据库 | 缓存与会话 |
"""

# Mid-bad layout: phrases wrapped across rows + leaked dash rules as body rows.
_FRAGMENTED_ABAC = """
| 超管将授权能力分 |     | 通过用户组的方式  |     |           |     |
| -------- | --- | --------- | --- | --------- | --- |
| 配合各个分级管理 |     | 给用户/组织授权。 |     | 用户/组织的权限。 |     |
| 员、系统管理员。 |     |         |     |         |     |
|     | 管理员授权 |     |     |     |     |
|     | 超管下放授权权限 |     | 分级/系统管理员授权 |     | 管理员管理权限   |
| --- | -------- | --- | ---------- | --- | --------- |
|     | 用户申请权限   |     | 管理员审批申请    |     | 管理员管理用户权限 |
| 用户自主申请 |     |     |     |     |     |
| 用户通过申请用户组权 |     |     | 在我的审批入口查 |     | 管理员添加、收 |
| ---------- | --- | --- | -------- | --- | ------- |
| 限或自定义权限获得操 |     |     | 看待办单据，审批 |     | 回用户权限。  |
| 作权限；       |     |     | 用户提交的申请。 |     |         |
| 通过申请分级管理员获 |     |     |     |     |     |
| 得授权权限。 |     |     |     |     |     |
"""

# License brochure: many tiny table shards + single-char lines between them.
_FRAGMENTED_LICENSE_PAGE = """
许可管理

|     |     | 01  | 02  |
| --- | --- | --- | --- |
核心能力
|     |     | 工作原理 | 精细管控 |
| --- | --- | ---- | ---- |
产品视角：各产品可以制定适合自身产品特性的
嘉为蓝鲸许可管理，是结合嘉为蓝鲸产品的商业
售卖策略，通过功能、资源的合理组合，形成产
| 理   |     | 种产品的许可管理场景。 |     |
| --- | --- | ----------- | --- |
精
| 原   |     |     | 组合各个产品，形成产品矩阵。 |
| --- | --- | --- | -------------- |
细
作
工 管
控
| 领   | License | 03  | 04  |
| --- | ------- | --- | --- |
域
驱
| 动   |     | 通信安全 | 领域驱动&简易接入 |
| --- | --- | ---- | --------- |
& 全
简 安
信
| 易   |     | 端到端之间的通信，均使用加密算法处理。许可 | 遵循领域驱动设计原则，领域内高内聚，领域间 |
| --- | --- | --------------------- | --------------------- |
通
接
|     |     | 文件，采用golang语言实现，避免许可文件被反 | 松耦合。提供Python SDK包、Java SDK包快速接 |
| --- | --- | ------------------------ | ------------------------------ |
入
|     |     | 编译后进行分析和伪造。 | 入。  |
| --- | --- | ----------- | --- |
"""


def test_fragmented_cmdb_layout_table_detected():
    assert is_fragmented_table(_FRAGMENTED_CMD_B) is True


def test_fragmented_backend_framework_table_detected():
    assert is_fragmented_table(_FRAGMENTED_BACKEND) is True


def test_fragmented_abac_wrapped_phrases_detected():
    assert is_fragmented_table(_FRAGMENTED_ABAC) is True


def test_fragmented_license_page_shards_detected():
    assert is_fragmented_table_markdown(_FRAGMENTED_LICENSE_PAGE) is True


def test_normal_org_table_not_fragmented():
    assert is_fragmented_table(_NORMAL_ORG) is False


def test_normal_simple_table_not_fragmented():
    assert is_fragmented_table(_NORMAL_SIMPLE) is False


def test_page_markdown_detects_any_bad_table():
    page = "# title\n\n" + _NORMAL_SIMPLE + "\n\n" + _FRAGMENTED_BACKEND
    assert is_fragmented_table_markdown(page) is True
    assert is_fragmented_table_markdown("# only\n\n" + _NORMAL_SIMPLE) is False
    assert is_fragmented_table_markdown("no tables here") is False


_FRAGMENTED_STABILITY_PROSE = """
稳定特性：Agent进程监管，平台自监控
对于系统的性能上的损耗很低，在没有作业调用执行的心 服务器性能 数据链路
系统性能损耗低 情况下，正常是在1%左右，执行作业的时候cpu和内存会 后台服务 依赖周边组件
升高。
当cpu占用超过10%或者men占用10%,代理将会启动重启
代理占用服务保
护
机制，保护系统的稳定性，待资源使用率恢复正常后，代
理将自动恢复。
当业务处于高峰时段，即cpu使用率达到85%时，代理也
系统占用服务保
护 将暂停运行。待资源使用率恢复正常后，代理将自动恢复。
支持Agent端数据采集快照，针对数据进行纠错、补录、
数据传输保障
断链重传，报文、数据、文件进行容错检测
Agent管控机制 平台自监控机制
负载均衡技术
高可用技术
容灾特性：自动秒切的容灾架构
高可用采控设计
实时/定时同步数
分布式服务设计
据库
"""

_NORMAL_PROSE = """
# 稳定特性说明

蓝鲸平台对系统性能损耗很低。在没有作业调用执行的情况下，CPU 占用通常约 1%；
执行作业时 CPU 与内存会有所升高。

当 CPU 占用超过 10% 或内存占用超过 10% 时，代理会启动重启保护机制，
待资源使用率恢复正常后自动恢复。

平台支持 Agent 端数据采集快照，并在断链时进行重传与容错检测。
"""


def test_fragmented_stability_prose_detected():
    assert is_fragmented_prose_markdown(_FRAGMENTED_STABILITY_PROSE) is True
    assert should_rasterize_pdf_page(_FRAGMENTED_STABILITY_PROSE) is True


def test_normal_prose_not_fragmented():
    assert is_fragmented_prose_markdown(_NORMAL_PROSE) is False
    assert should_rasterize_pdf_page(_NORMAL_PROSE) is False


# 节点管理产品架构：功能块被拆成稀疏表（可无 dash 泄漏行）
_FRAGMENTED_NODE_ARCH = """
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


def test_fragmented_node_architecture_sparse_grid_detected():
    assert is_fragmented_table(_FRAGMENTED_NODE_ARCH) is True
    assert should_rasterize_pdf_page("# 节点管理产品架构\n\n" + _FRAGMENTED_NODE_ARCH) is True


def test_salvage_node_architecture_to_label_list():
    out = salvage_sparse_layout_table(_FRAGMENTED_NODE_ARCH)
    assert out is not None
    assert "- Agent管理" in out
    assert "- Agent状态管理" in out
    assert "- Proxy安装" in out
    assert "|" not in out


def test_salvage_skips_normal_tables():
    assert salvage_sparse_layout_table(_NORMAL_SIMPLE) is None
    assert salvage_sparse_layout_table(_NORMAL_ORG) is None
