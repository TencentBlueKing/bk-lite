# ITSM 审查修复与本地验收记录

日期：2026-11-12。仓库：`weops-lite/bk-lite`，分支：`feature_itsm`。提交范围仅包含本轮 ITSM 修复、测试及验收记录；未推送远端。

## 范围与完成项

对照本地 `itsm4/bk-itsm` 的动态提单、节点字段权限、审批、自动活动和生命周期行为，修复本轮审查发现的问题；本文不代表 ITSM4 全量功能等价认证。

- [x] P1：工单对象可见范围、租户范围、处理人/代理授权；用户名 admin 不再构成超管旁路。
- [x] P1：表单、流程、基础设置、SLA、处理组、通知模板及扩展资源的读写权限分离；服务、设计、数据表等已修入口按租户过滤。
- [x] P1：服务与流程归属校验先于启动实例；只读/隐藏字段不接受客户端覆写，隐藏字段不随详情返回。
- [x] P1：节点提交合并原表单，真实审批动作按节点类型选择；认领任务保留待办，终态清理 pending/claimed。
- [x] P1：挂起/恢复同步引擎；转单/交接同步处理人；退回、撤销、重开操作同一业务工单。状态不允许的操作先拒绝，避免先终止引擎再校验失败。
- [x] P1：自动节点先执行再 ACK；失败不推进，重复 ACK 不重放业务动作；补偿轮询同步引擎异步生成的后续任务。
- [x] P1：Flowable 写请求超时不盲目重试；自动 HTTP 请求不跟随重定向；打印模板沙箱执行并转义工单字段。
- [x] P2：门户及工单中心使用动态申请表单，内联必填校验；待办/状态/分页在服务端执行，分页上限 100。
- [x] P2：详情操作随权限和状态显示，挂起禁用表单；自动节点结束后刷新任务；只允许创建人提交满意度。
- [x] P2：子表单行编辑、签名姓名确认、子流程申请与关联子单、标签页/分组递归渲染；父分组只读权限向下继承。
- [x] P2：完整表单草稿/模板保存和恢复，本地缓存按用户隔离，远端草稿按用户/域隔离并加事务锁。
- [x] P2：画布往返保留节点字段权限、自动配置和流程 settings；新发布流程保存表单快照，避免后续改表影响该版本。
- [x] 触发器匹配事件别名与条件，状态动作真实更新。

## 验证结果

| 验证 | 结果 |
|---|---|
| ITSM 后端测试（PostgreSQL 独立 test_bklite，含真实 Flowable） | 86 passed |
| 后端变更可执行行覆盖率（包含新源文件，排除测试文件） | 546 / 656 = 83.23% |
| 前端 Vitest：动作、配置往返、结构化控件、嵌套表单 | 8 passed |
| `pnpm exec eslint src/app/itsm` | 通过 |
| `pnpm type-check` | 通过；现有 isoflow 包体积及 Node 版本提示未阻断 |
| `git diff --check` | 通过 |
| 实际 HTTP 对象越权 | 无关用户详情/修改均 404；admin 详情 200，金额仍为 200 |

后端命令使用运行中 Django 的配置、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`ITSM_FLOWABLE_TEST=1`：

```sh
.venv/bin/python -m pytest -c /dev/null --noconftest \
  -p pytest_django.plugin -p pytest_cov.plugin -p no:cacheprovider \
  --nomigrations --reuse-db apps/itsm/tests --cov=apps.itsm \
  --cov-report=json:/tmp/itsm-coverage.json -q
```

四条真实引擎测试分别覆盖：

1. 提单 → 或签审批 → 人工处理 → 完成。
2. 自动写表 → 后续人工任务同步 → 认领/审批 → 完成。
3. 挂起/阻止提交 → 恢复 → 转单/原处理人拒绝 → 退回提单 → 撤销 → 重开。
4. 十节点：提单 → 决策表 → 分支 → 并行处理 → 汇聚 → 通知 → 完成；通知投递在该测试中使用 stub，实际站内通知另外由浏览器闭环验证。

## 本地服务与浏览器闭环

使用前端 3000、Django 8000、PostgreSQL 55432/bklite、Redis 6379/1、Flowable 8088。

- 工单 27：浏览器动态表单提交，保存金额、表格行、签名；审批时只读字段禁用，修改金额至 150，自动写表后人工完成。
- 工单 28：门户提交金额 200 → 挂起 → 表单/动作禁用 → 恢复 → 提交 → 审批 → Redis/Celery 自动写表 → 最终处理 → 完成 → 满意度 5 分。
- ORM 与引擎复核：27/28 均为 finished，实例已结束，活动任务数为 0，各有一条完成的自动执行记录，数据表共两条结果。
- 工单 29：未手动调用 auto_tick，由专用 Beat 每 30 秒投递，Worker 执行并同步最终处理节点；已完成，自动执行 done=1，活动任务数=0。Beat 日志记录 08:05:27 / 08:05:57 UTC 的定时投递。
- 草稿浏览器刷新验证：标题、金额 375、签名均恢复。
- 无关用户 HTTP 验收账号已禁用；保留原审查测试账号和用户要求设置的 admin。凭据不写入仓库。
- 浏览器截图：`itsm-fixed-portal-finished.png`、`itsm-fixed-draft.png`，位于当前会话的本地 visualizations 目录。

为本地自动推进保留只消费 `itsm-review` 队列的 Worker，以及每 30 秒仅投递 `apps.itsm.tasks.auto_tick` 到该队列的专用 Beat。Beat 使用 `/tmp/itsm-local-beat-schedule`，日志为 `/tmp/itsm-local-beat.log`。未启用全站邮件、作业或其他模块定时任务；此为当前机器开发进程，不是生产部署配置。当前 Beat PID 79426，Worker PID 79498；需要停止时可向这两个进程发送 TERM。

## 完整仓库门禁的限制

已运行门禁，不标记为全仓通过：

- `pnpm lint`：3 errors / 102 warnings。错误位于未修改的 `automaticPolicyApply.ts`、`components/rum-bootstrap.tsx`、`utils/rumBootstrap.ts`，均为 type/interface lint 规则。日志 `/tmp/itsm-web-gate.log`。
- `make test`：环境附加 `PYTEST_ADDOPTS='--maxfail=1 --nomigrations --no-cov'`、`UV_NO_SYNC=1`。应用测试 104 passed / 5 skipped / 1 failed，停止于 alerts 的 `test_alert_list_counts_events_without_loading_event_details`（PostgreSQL transaction aborted）。独立 PPT 工具测试 719 passed / 3 skipped / 23 failed，涉及 `/tmp` 与 `/private/tmp` 路径及模板选择/确认行为。日志 `/tmp/itsm-server-gate-final.log`，JUnit 为 `server/test-results/{server,ppt-skill}.xml`。这些模块未做顺手修复。

## 兼容、边界与回退

- 读权限不能继续调用配置写接口，调用方需现有对应菜单的写权限；不保留不安全旁路。
- 无 schema migration；`init_itsm` 增加挂起到撤销/关闭/终止的内置流转，本地已执行。
- 新发布版本带表单快照；旧版本缺快照时仍按原契约使用当前表单，未擅自重写历史版本。
- 子流程表单最多 20 个子单，禁止递归创建；签名当前是姓名确认，未宣称具备手写签章/法律认证能力。
- 自动动作结果不确定时不盲目重放外部副作用；外部作业、编排、CMDB 和对象存储等未列出的服务，不包含在本地真实闭环验收中。
- 回退旧应用会重新暴露已确认权限问题，需先暂停相关写入口再回退。未修改用户的真实业务工单；验收工单均为测试标记。

提交前复核：仅暂存 ITSM 后端、前端、测试与本记录，共 41 个文件。按 pre-commit 清理未使用导入并拆分重开工单方法后，86 项后端测试重新通过。
