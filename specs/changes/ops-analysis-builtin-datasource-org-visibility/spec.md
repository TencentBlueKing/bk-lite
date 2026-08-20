# 运营分析内置数据源组织可见性

Status: ready

## Problem Statement

运营分析的内置数据源几乎都是平台 NATS 接口目录，本身没有组织私有凭据。取数时已经注入当前组织与权限，由下游按数据范围过滤。但目录本身仍按 `groups` 隔离：初始化只写入 Default 组织，其它组织默认看不到、也不能选用这些内置源。每新增一个组织都要人工补可见性，否则内置接口形同未交付。

与此同时，少数内置 NATS 接口可能敏感，部署方仍希望能收到指定组织，而不是永远全员可见。

## Solution

把内置数据源的所属组织改成可见性白名单，并允许为空：

- 空名单表示全员可见、可选用、可取数。
- 非空名单表示仅这些组织可见。
- 内置定义（名称、接口、参数、字段等）仍不可改、不可删；前端只开放组织字段给超管修改，并提示空名单即全员可见。
- 自定义数据源继续必选组织；空名单对自定义源仍视为不可见。

存量内置源若仍是种子写下的 Default 单组织，一次性清成空名单，使新组织无需配置即可使用。已经改成其它组织组合的名单予以保留。

## User Stories

1. As a 任意组织的运营分析使用者, I want 在未配置组织名单的内置数据源目录中看到并选用平台 NATS 接口, so that 新组织不必等待有人补可见性就能搭画布。
2. As a 超管, I want 把某个内置数据源的所属组织改成指定组织或清空, so that 敏感接口可以按组织收口，普通接口可以恢复全员可见。
3. As a 超管, I want 在数据源管理列表中看到全部内置源（含已收口到其它组织的）, so that 改完可见性后还能找到它们并再次调整。
4. As a 非超管的数据源管理者, I want 查看内置数据源但不能改所属组织, so that 任意组织的编辑权限不能把全平台目录锁成自家。
5. As a 组织 B 的使用者, I want 当内置源已收到组织 A 时在目录和取数中都不可见, so that 组织白名单对列表、画布绑定和运行时取数一致。
6. As a 自定义数据源管理者, I want 创建或更新时仍然必须选择组织, so that 漏传空名单不会把自定义源变成全平台目录。
7. As a 平台运维, I want 重复初始化既不覆盖已收口的组织名单、也不把空名单补回 Default, so that 升级不会打回全员可见或敏感收口。

## Implementation Decisions

### 可见性语义

- 仅 `is_build_in=true` 的数据源把空 `groups` 解释为全员可见。
- 自定义数据源：空 `groups` 不可见；创建与更新拒绝空数组。
- 非空 `groups`：当前组织必须在名单中，才可在目录中出现、绑定画布、预览或取数。
- 该谓词必须同时用于列表、详情、预览、运行时取数、分享/报告渲染取数，以及其它现有的「当前组织必须在 `groups` 中」检查；不得只改前端提示。
- 取数仍注入当前组织的用户与权限信息；组织白名单只控制目录可见性，不替代下游 NATS 鉴权。同 path 的自定义 NATS 数据源不在本变更拦截。

### 权限

- 改内置数据源 `groups`（含清空）仅超管。非超管对内置源的组织 PATCH 返回 403。
- 内置源的内容字段更新与删除继续拒绝。
- 超管在数据源管理列表可见全部内置源，不受当前组织名单限制，否则收口后无法再管理。
- 画布取数、预览、组件绑定不为超管开旁路：名单非空且当前组织不在其中时，超管同样 403。超管要取受限源，须切到名单内组织。

### 初始化与存量

- 新建内置数据源时 `groups=[]`。
- 升级/强制初始化保留已有非空名单；空名单保持为空，不再回填 Default。
- 为运营分析空 `groups` 补 Default 的初始化必须跳过内置数据源。
- 一次性把「内置且名单为空或仅为根 Default 组织」清成 `[]`。名单已含其它组织（即使同时含 Default）则保留。

### 前端

- 内置数据源对超管可进入编辑，但只有所属组织可改；名称、类型、接口、参数、字段等保持只读，无删除。
- 非超管对内置源仍为查看：能看到组织，不能改。
- 内置源的组织字段非必填；空选择旁提示「未选择组织表示所有组织可见」。
- 自定义源组织仍必填。
- 保存内置源只提交组织字段，不得带上其它只读字段走完整更新。

### 与既有生命周期能力的关系

- 本变更只改内置数据源的 `groups` 语义与种子默认值。
- 内置目录、仪表盘、大屏、报表、拓扑、架构图仍按现有规则：新建用 Default，更新保留 `groups`，有编辑权的调用方可 PATCH 组织可见性。
- 落地后须把长期能力中「内置数据源与内置画布共用 Default 种子」的表述改成上述分流，避免后续初始化再把空名单写回 Default。

## Testing Decisions

- 只测对外行为：列表是否出现、取数/预览是否 403、PATCH 是否只允许超管改组织、初始化是否保留或清空名单。不测私有谓词实现细节。
- 最高测试缝：数据源列表、详情、预览、运行时取数、内置组织 PATCH、初始化命令。前端补组织字段可选、内置只提交组织、非超管只读的契约或组件测试（若已有数据源设置页测试风格）。
- 先验：内置源只允许组织 PATCH、非超管不能改可见性、初始化回填/保留 `groups` 的现有数据源与管理命令测试。本变更将推翻「空名单补 Default」的期望，须改成「内置空名单保持为空」。
- 必覆盖场景：空名单内置源对组织 A/B 均可列出并取数；收到组织 A 后组织 B 列表与取数均不可见；超管可列出已收口源并清空名单恢复全员；非超管 PATCH 组织 403；自定义源拒绝空组织；重复初始化不改已收口名单、不把空名单补成 Default；存量仅为 Default 的内置源被清成空名单，含其它组织的名单保留。

## Out of Scope

- 内置画布、目录的「空 = 全员可见」。
- 拆成平台目录与组织数据源两套对象。
- 在运营分析层拦截同 path 自定义 NATS。
- 把空名单语义扩大到自定义数据源、数据连接库或命名空间。
- 新的独立权限位（沿用超管判断）。
- 按组织隐藏后的申请开通流程。

## Further Notes

- 前端画布侧已有「数据源 `groups` 为空则全员有权」的展示判断，与后端列表/取数长期不一致。本变更让后端内置源与该语义对齐；自定义源不得跟过去。
- 命名空间本来就是平台共享、无组织归属；内置 NATS 空名单与之同类。数据连接库继续按组织隔离，本变更不开放跨组织共享连接。

### 落地验证（2026-08-20）

后端（`server/`，`uv run pytest … -v --no-cov`）：**146 passed, 12 failed**（40.92s）。

与本变更相关且通过：`test_datasource_visibility.py`（3）、`test_datasource_filters_serializers.py`（含空组织校验）、`test_clear_default_only_builtin_datasource_groups.py`（3）；`test_datasource_view.py` 可见性/列表/取数/超管 PATCH 相关用例（空名单内置可列可取、受限内置对其他组织 403、超管列表可见受限源、超管取数无旁路、非超管改组织 403、超管可清空 groups）；`test_management_commands.py` 的 `keeps_empty_groups_on_existing_builtin`、`skips_builtin_datasource`、`keeps_existing_non_empty_groups`。

既有基线失败（预览 / 无关 mock，本任务不修）：

- `test_datasource_view.py`（6）：`test_get_source_data_wraps_inline_datasources_in_transport_envelope[mysql|postgresql|rest_api|excel]` 返回 502（SimpleNamespace 缺 `transform_config`）；`test_get_source_data_rejects_namespace_when_datasource_has_no_namespaces`、`test_get_source_data_rejects_unassociated_namespace` 期望 400 实得 403（`IS_LOCAL_RPC` 本进程取数）。本轮未复现 PG `FOR UPDATE`。
- `test_datasource_preview_views.py`（4）：`test_preview_saved_datasource_requires_edit_permission[data_source-Edit-200]`、`test_preview_saved_datasource_uses_persisted_config`、`test_get_source_data_executes_inline_datasource`、`test_get_source_data_returns_saved_excel_items`，均为 502 / SimpleNamespace 缺 `transform_config`。
- `test_management_commands.py`（2）：`test_batch_init_warns_and_continues_when_default_namespace_config_is_invalid`（Default 组织 unique）；`test_init_source_api_data_creates_cloud_cost_distribution_contract`（云成本 JSON 契约，`alias_name` 排行主体 vs 分组维度）。

前端（`web/`，`pnpm exec vitest run …`）：**3 files / 20 tests passed**（2.82s）——`operateModalUtils.extract.test.ts`、`builtinVisibility.test.ts`、`permissionChecker.test.ts`。

终审补丁（同日）：分享会话 `data_sources` 与数据源 `retrieve` 改用 `can_access_datasource_in_org`。空名单内置进入分享目录；收口到其它组织的内置对分享空间隐藏；超管可打开受限内置详情（管理列表），取数仍无超管旁路。相关用例 6 passed（`test_share_datasource_includes_empty_groups_builtin`、`test_share_datasource_excludes_restricted_builtin_outside_space`、三条 retrieve，以及既有 scoped metadata）。
