# 监控 → CMDB 同步任务（关联 + 确认新建）

Status: implemented

## Problem Statement

监控里已经有一批实例，CMDB 还没有台账，或两边身份没对上。今天主机创建钩子和隐藏的 `push_to_cmdb` 会静默 ingest，可能直接建 CI 或改字段；列表上又没有可回来的任务。运维无法从监控勾选、先看关联结果、再决定要不要把缺失的台账建出来。

## Solution

在监控资产列表做「同步到 CMDB」：勾选后进入胶水任务。先只写关联指针，不改已有 CI 字段。已经关联的进「已关联」桶，第一期没有「同步数据」。CMDB 没有的进「待新建」，人确认后再用监控已有的名称、IP、云区域、组织建 CI，并写回成对指针。凭据不进 CMDB。无内置反向映射的对象、平台树对象不进本任务。

## User Stories

1. As a 监控管理员, I want 在资产列表勾选实例后生成「同步到 CMDB」任务, so that 我能回来看关联和待新建，而不是点一下就静默写库。
2. As a 监控管理员, I want 任务先按已有 `cmdb_id` 和该对象身份规则自动关联且不改台账字段, so that 已经对上的 CI 不会被监控侧名称或组织覆盖。
3. As a 监控管理员, I want 已关联的勾选项进「已关联」桶且第一期不能覆盖字段, so that 误勾已绑定实例也不会改 CMDB。
4. As a 监控管理员, I want 「CMDB 没有」的行在确认后才新建 CI, so that 台账写入是一次明确操作。
5. As a 监控管理员, I want 身份冲突留在任务里手绑, so that 不会绑错。
6. As a 只装了监控或 CMDB 未授权的管理员, I want 看不到同步到 CMDB 的入口, so that 不会点进一个对端不存在的流程。
7. As an 平台管理员, I want 任务过一段时间自动消失且已写的关联还在, so that 记录不会一直堆着。

## Implementation Decisions

- 复用胶水模块 `module_link` 和许可继承（cmdb+monitor），不新开可售卖应用，不进顶栏。
- 反向任务与正向任务分表，不把 `MonitorLinkTask` 的 `waiting_access` 语义拧成「待新建」。
- 入口在监控资产列表；`clientData` 加载中 / 无 cmdb / 无 monitor / 当前对象不在内置反向映射 / 平台树对象，都不显示按钮。
- 内置反向映射只倒 `CMDB_MODEL_TO_MONITOR_OBJECT`（Host→host 等）。禁止使用 `resolve_cmdb_model_id` 那种「未知默认 host」。
- 第一段只写 `cmdb_id` / `monitor_id`。禁止调用会 upsert 字段的 `MonitorToCmdbPushService.push_instance`。现有 `POST .../push_to_cmdb/` 保留内部，UI 不接。
- 主机创建钩子的 best-effort ingest 不改；本任务处理漏网和未挂钩子的对象。
- 上限 100，同步跑完第一段，不上队列。
- 任务状态：有待新建行则为 `waiting_create`，否则 `completed`；取消不拆已写指针。
- 行状态：`already_linked`、`ok`（本次新绑）、`not_found`、`conflict`、`failed`、`skipped_model`。
- 关联规则：已有成对 ID 且对端还在 → already_linked；Host 用 IP+云区域唯一命中；其它对象用该模型已有身份规则或唯一实例名；多命中 → conflict。
- 确认新建：只处理勾选的 `not_found` 行；写入名称 / IP / 云区域 / 组织 / `monitor_id`；不带凭据、不重采、不进通用待审批、不覆盖未勾选行。监控实例未填 `cloud_region_id` 时，先用关联 Node，再按 IP 唯一命中节点，再落到监控默认云区域（`default` / id=1）。host 新建必带 `cloud`。主机 IP 先用实例 IP，再用 `summary_facts.asset.ip`，再用关联 Node IP。组织只写当前 actor 范围内的 ID，超出范围的组织丢掉，避免 CMDB 范围校验把整行打成失败。内置同步模型里只有 host 额外必填 `ip_addr`+`cloud` 且唯一规则是 IP+云区域；其它对象必填只有实例名和组织，端口不是必填，确认新建不写凭据也不为可选端口专门去采集配置里翻。
- 冲突手绑复用现有 CMDB 候选绑定，不自动合并。
- 回收与正向共用 7 天 Beat，CASCADE 删任务行，不拆指针。
- 写任务要监控实例操作权；确认新建还要 CMDB `asset_info-Edit`。无权行记 `failed`，不整批 403。
- 每一行带 `message` 给任务页「原因」列。业务异常（`BaseAppException.message`）原文上屏；其它失败只用稳定短句。不把 RuntimeError / payload / 凭据写到页面。已有失败任务不会回填原因，需重新同步。

## Testing Decisions

只测外部行为：建任务、第一段分桶且已有 CI 字段不变、已关联不进待新建、无映射对象无入口或进 skipped、确认后只新建勾选行并回写指针、未确认不建 CI、冲突不自动合并、取消不拆指针、无 CMDB 许可时入口隐藏、过期任务 404 且指针仍在。不测页面像素。

测试缝：胶水任务服务、HTTP 视图、入口 fail-closed、倒映射表。Prior art：`apps/module_link/tests/`、`test_monitor_link_bind.py`、`test_push_to_cmdb.py`、`systemLinkage.test.ts`。

## Out of Scope

- 用监控覆盖已有 CI 的名称 / IP / 组织 / 云区域（交互稿「同步数据」屏）。
- 未关联跨任务收件箱。
- 修改主机创建钩子或退役 `push_to_cmdb`。
- 第一期为无映射对象手指定 CMDB 模型。
- K8s / 云 / vCenter 子对象一对一台账。
- 把监控凭据或采集配置写入 CMDB。

## Further Notes

- 正向规格仍是 `specs/changes/cmdb-monitor-link-task/spec.md`。
- 交互稿 `docs/design/product-decisions/cmdb-monitor-link-task.html` 的反向「同步数据」屏属于后置，第一期只做到分桶 + 确认新建。
- 产品记忆：`docs/design/product-decisions/cmdb-monitor-link-task.md`。
- 验证：`uv run pytest apps/cmdb/tests/test_monitor_link_catalog.py apps/module_link/tests/test_monitor_cmdb_task.py apps/module_link/tests/test_monitor_cmdb_views.py apps/module_link/tests/test_constants.py apps/monitor/tests/test_push_to_cmdb.py --no-cov` 通过；`pnpm exec vitest run src/app/cmdb/utils/__tests__/systemLinkage.test.ts` 通过；`pnpm type-check` 通过。未在浏览器里点通登录后的资产列表。
