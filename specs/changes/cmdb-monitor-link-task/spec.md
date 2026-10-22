# CMDB → 监控同步任务（单向先做）

Status: implemented

## Problem Statement

运维在 CMDB 录了一批资产，希望尽快和监控对上。今天要么走扫描带凭据双向推，要么两边都录且身份一致才自动关联。列表「同步到监控」只能无凭据认领、对不上就散掉；凭据不契合时整条路卡住。未关联、冲突、监控侧根本没有对象，没有一个任务能接着处理。

## Solution

先做 **CMDB → 监控的单向同步任务**。勾选资产后生成任务：先按现有身份规则自动关联；再把「CMDB 有、监控没有」的对象按监控插件分组，生成接入草稿，跳到监控接入页预填身份，由人补凭据和采集项后批量接入。任务不在 CMDB 侧发明 Telegraf 配置，不无凭据暗建监控实例。

反向（监控 → CMDB）不在本变更实现。第一期反向（关联 + 确认新建，不覆盖字段）见 `specs/changes/monitor-cmdb-link-task/spec.md`。

## User Stories

1. As a CMDB 管理员, I want 勾选一批资产后生成「同步到监控」任务而不是当场散掉结果, so that 我能回来看关联、待接入和冲突。
2. As a CMDB 管理员, I want 任务先把身份一致的实例自动关联且不开采集, so that 监控已有对象时不必再走接入。
3. As a CMDB 管理员, I want 待接入时先选该对象下的接入模板再预填, so that 我能用自己 DIY 的模板而不是被绑死在内置插件上。
4. As a CMDB 管理员, I want 身份冲突留在任务里手绑或改身份而不是自动合并, so that 不会绑错。
5. As a 监控管理员, I want 以后从监控勾选同步到 CMDB 时同样先关联再确认是否写入台账字段, so that 凭据留在监控、CMDB 只收配置事实。
6. As a 只装了 CMDB 或监控未授权的管理员, I want 看不到同步到监控的入口, so that 不会点进一个对端不存在的流程。
7. As an 平台管理员, I want 同步任务过一段时间自动消失, so that 任务记录不会一直堆着；已经建好的关联还在。
8. As a CMDB 管理员, I want 自定义模型或没有内置映射的模型能指定对到哪个监控对象, so that 没有写死关系时仍能同步，而不是系统替我猜。

## Implementation Decisions

- 任务页、任务/草稿表、编排与回收独立成胶水模块 `module_link`，不进 CMDB 核心也不进监控核心；不是新的可售卖应用，不出现在顶栏应用列表。每一行带 `message` 给任务页「原因」列：业务异常原文上屏，其它失败只用稳定短句，不把 payload / 凭据写到页面。
- 对端模块当前用户识别不到许可（`clientData` 无 `monitor` / 无 `cmdb`）时，同步入口不出现；加载中也不闪一下。服务端始终装入胶水模块，不按对端是否安装动态挂载。企业版许可闸默认把 `/api/v1/module_link/` 当成独立 SKU；OSS 将其豁免，并要求 cmdb 与 monitor 同时授权后才放行胶水接口。
- 本期只实现 CMDB → 监控。反向第一期另开 `monitor-cmdb-link-task`：同一胶水壳，第二段是确认新建 CI，不做字段覆盖。
- 任务分两段，中间等人：① 自动关联（已有 ID → 类型身份，无凭据、不新建）；② 待接入草稿（按 Host / Switch / Mysql 等监控对象分组）。
- 全选可以跨模型勾，草稿必须一组一个插件；异构对象不能进同一张接入表。
- 「去配置」先落到该监控对象的模板列表（复用接入页插件卡片，含内置和 DIY），人选模板后再带草稿 ID 进接入页。不默认同名内置插件。预填名称、IP、云区域、组织、`cmdb_id`。凭据、节点、间隔、采集项由人按所选模板补。提交走监控现有批量接入。
- 内置一对一映射表只覆盖已知模型，不因自定义模型去改那张常量。无映射的自定义模型进任务「待指定对象」桶：人选定监控对象后才生成草稿；可选记住该模型默认对谁（存在胶水模块，不写进 CMDB/监控核心）。指定后的自动关联：已有 ID，以及该对象下唯一实例名；只有选中的对象本身已有内置身份规则（如 Host 的 IP+云区域）才套用，不把 Host 规则套到任意自定义对象。
- K8s / 云账号 / vCenter 仍不走「指定对象」捷径，保持 skipped（平台入口另案）。
- 监控已有实例只关联，不进入接入草稿，避免双建。
- K8s / 云账号 / vCenter 不进本任务的子对象草稿；入口实例另案（手绑 + 原生键扇出）。
- 告警策略不是本任务主产物；默认规则仍由监控接入链路创建。
- 不复制扫描那条带密创建路径。系统管理凭据仓库可在接入页选用。
- 现有列表 100 条无凭据同步收成任务第一段；详情手绑留给冲突行，仍留在 CMDB 详情。
- 任务与草稿延时回收：创建 7 天后由周期任务删除记录；不拆已经写上的 `monitor_id` / `cmdb_id`。

## Testing Decisions

只测外部行为：建任务、第一段关联结果分桶、已有监控实例不进草稿、草稿按对象类型分组、去配置先选模板再预填、冲突不自动合并、取消任务不改已关联指针、对端模块不可见时入口隐藏、过期任务被回收且关联指针仍在、无映射模型指定对象后才出草稿、内置常量映射表不因自定义模型被改写。

Prior art：`test_monitor_link_batch.py`、`test_monitor_link_bind.py`、`test_push_to_monitor.py`、`test_module_ingest.py`。

## Out of Scope

- 监控 → CMDB 任务（另开 `specs/changes/monitor-cmdb-link-task/`）。
- 无凭据暗建监控实例或策略。
- 在 CMDB 生成 Telegraf / 插件配置并直推。
- 把监控插件凭据写入 CMDB 采集任务。
- K8s / 云 / vCenter 子对象一对一接入草稿。
- 扫描工作队列改造。

## Further Notes

- 叠在 `cmdb-monitor-manual-bind-batch-sync` 之上，不取代自动认领。
- 交互稿：`docs/design/product-decisions/cmdb-monitor-link-task.html`。
- 产品记忆：`docs/design/product-decisions/cmdb-monitor-link-task.md`。
- 反向第一期：`specs/changes/monitor-cmdb-link-task/spec.md`。
