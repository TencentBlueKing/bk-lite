# 被动接收日志提取器

Status: implemented

## Problem Statement

syslog 与 snmptrap 是被动接收日志：设备把日志打到共享接收口，接入页只展示节点和目标地址，不会创建日志采集实例。现有提取器只能绑定采集实例，并按事件 `instance_id` 匹配，因此这两类日志无法配置提取规则。运维人员还希望在日志搜索里选中一条具体日志后直接去创建提取器，并按这条日志的类型跳到正确作用域。

## Solution

为 syslog / snmptrap 提供采集类型级提取器：全部 syslog 一套规则，全部 snmptrap 一套规则，运行时按 `collect_type` 匹配。接入详情左侧增加与实例提取器相同的表格页。搜索页对当前这条日志提供「创建提取器」：被动接收类型跳到类型级新建页，其他类型跳到该日志所属采集实例的提取器新建。

## User Stories

1. As a 日志运维人员, I want to manage ordered extractors on the syslog and snmptrap access pages, so that I can turn passively received log text into searchable fields without inventing collection instances.
2. As a 日志运维人员, I want those rules to apply to every event of that collect type, so that a shared receiver does not require per-device instances.
3. As a 日志运维人员, I want to narrow a type-level rule with existing structured conditions such as hostname, source_ip or node_ip, so that I can still distinguish sources inside the shared pipe.
4. As a 日志运维人员, I want to create an extractor from the currently selected search hit, so that I can start from a real event instead of copying fields by hand.
5. As a 日志运维人员, I want syslog/snmptrap search hits to open the type-level create form and other collect types to open that hit's instance extractors, so that the destination matches how those logs actually belong.
6. As a 日志查看者, I want to inspect type-level rules, samples and preview when I can enter log integration, without being able to change them unless I also have configure permission on the current team.

## Implementation Decisions

- 不为 syslog / snmptrap 创建虚拟采集实例，也不把采集侧写死的 `instance_id = "base"` 当成业务对象。
- 提取器作用域互斥：一条规则要么绑定日志采集实例，要么绑定采集类型。类型级只允许 `syslog` 和 `snmp_trap`。名称、连续顺序和 20 条上限按作用域计算，与实例级相同。
- 规则业务模块继续作为 CRUD、调序、预览、样本和一次事务一次发布的外部接口。新增类型级入口，不另起发布模块。实例级接口保持原参数；类型级用采集类型名 `collect_type`，不能与 `collect_instance` 同时出现。
- 中心 Vector 编译：实例规则仍匹配 `.instance_id`；类型规则匹配 `.collect_type`。发布快照包含两类规则。失败跳过、保护字段、全局 generation 和上一份有效快照语义不变。不改 fusion-collector / 采集侧 Vector。
- 类型级样本查询 `collect_type:"syslog"` 或 `collect_type:"snmp_trap"`，复用现有搜索默认窗口和条数上限。预览不伪造实例身份。
- 类型级授权走日志集成页面权限，不新建权限模块：能解析 `current_team` 且拥有 `integration_configure-View`（或 `integration_list-View`）可看；拥有 `integration_configure-Add` 可写。无 `current_team` fail closed。超级管理员沿用现语义。实例级仍按采集实例 View/Operate 授权。
- 接入详情仅对 syslog / snmptrap 增加「提取器」侧栏项。表格、弹窗、预览和发布状态复用实例提取器实现，页面形态而不是再做一套表单。
- 搜索页「创建提取器」只针对当前这一条日志，用该事件做预览样本，不从选中文本反推正则。分流以 `collect_type` 为准：`syslog` / `snmp_trap` 永远走类型级页。其余类型使用事件 `instance_id`；缺失、实例不存在或当前团队对该实例无编辑权限则拒绝。实例级第一版跳到日志接收页并打开现有抽屉进入新建，不新增实例提取器路由。
- 测试接缝：规则业务模块（类型级 CRUD/调序/样本/预览/上限）、编译器（`.collect_type` 匹配且不误伤实例规则）、视图授权（页面权限与 `current_team`）、前端纯函数（搜索分流与跳转目标）。不测 Vector 内部、不穿透发布状态表。

## Testing Decisions

- 只通过规则模块、编译器、HTTP 视图和前端纯函数观察行为，不断言内部 helper 调用次数。
- 编译器用表驱动字面量断言 VRL 含 `.collect_type == "syslog"` / `"snmp_trap"`，且实例规则仍含 `.instance_id ==`。
- 类型级创建/调序/删除各只让全局 generation 增加 1；超过 20 条不标脏。
- 无 `current_team`、无配置页写权限的用户不能写类型级规则；有查看权限可列表。实例越权语义保持 403/404。
- 前端脚本覆盖搜索分流：syslog/snmptrap 忽略 `instance_id = "base"`；其他类型缺 `instance_id` 不可用；实例跳转带 `extractor` 与 `create=1`。
- 既有先例：`test_log_extractor_compiler_pure.py`、`test_log_extractor_rules_service.py`、`test_log_extractor_views.py`、`web/scripts/log-extractor-interaction-test.ts`。

## Out of Scope

- 按主机、接收节点或组织拆多套类型级规则包。
- 搜索页选中文本反推正则 / Grok / AI 生成规则。
- 历史日志重新提取。
- 为实例提取器新增独立路由页。
- 把搜索页创建入口以外的提取器能力做成按采集类型显隐矩阵。
- 修改采集侧 Vector、fusion-collector、webhookd 或 NodeMgmt 下发。

## Further Notes

- 修订已实现规格 `specs/changes/log-file-extractor/spec.md` 中「不允许创建无实例规则」和「不得从日志搜索页反向新建」两条；本变更只放开 syslog/snmptrap 的类型级规则，以及「从当前这条日志跳转创建」。
- 产品决策记忆：`docs/design/product-decisions/log-extractor-passive-collect.md`。
- 完成证据（2026-08-26）：
  - `uv run pytest apps/log/tests/test_log_extractor_compiler_pure.py apps/log/tests/test_log_extractor_rules_service.py apps/log/tests/test_log_extractor_views.py apps/log/tests/test_log_extractor_publication_service.py apps/log/tests/test_log_extractor_vector_contract.py --no-cov --nomigrations --create-db`：48 passed, 1 skipped（sqlite 全量 migrate 被仓库既有 `NewSessionEventRelation` 问题阻断，与本变更无关）。
  - `pnpm test:log-extractor-interaction`：passed。
