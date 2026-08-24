# APM 部署事件增量物化

Status: accepted

## 目标与范围

把首页「版本发布变更」从每次直查 VictoriaTraces 的 7 天聚合，改为读取 `ApmDeploymentEvent`。事实源仍是遥测：现有目录对账任务已经拉取近窗实例活动（含 `service.version`），本变更在同一周期里把 version 变化增量写入部署事件表。

本变更不新增一级「部署追踪」菜单、不接 CI/CD 上报、不把回填命令加入 `batch_init`。

## 领域语言

- **推断部署**：某服务在某环境下 `service.version` 相对该环境最新事件发生变化，由对账任务写入，`source=inferred`。
- **上报部署**：未来 CI/CD 写入，`source=reported`。本变更不实现写入路径。
- **上线时刻**：推断事件的 `deployed_at` 取该 version 在本对账窗口内最早一次 `last_seen_at`；一次性回填则用 VictoriaTraces `min(start_time)`。
- **部署人**：推断源为空；UI 不得假装有操作者。

接入页复制命令不落库，不产生部署事件。

## 写入

`reconcile_telemetry_catalog` 在目录发现成功后调用 `DeploymentEventRecorder`。无新增 Celery 任务、无新增 VictoriaTraces 查询。

对每个 `(service, environment)`：

- 无历史事件：按版本号升序写入当前窗口内出现的 version；多于一个时最新一条为 `in_progress`，其余为 `success`。
- 最新事件 version 仍在窗口内且出现更高 version 或同级不同字符串：新建事件，状态 `in_progress`。窗口内残留更低 version 不记回滚。
- 最新事件 version 已离开窗口且出现更低 version：新建 `rollback`。
- 最新事件 version 已离开窗口且出现更高 version：新建 `success`。
- 最新事件 version 未变：不新建。
- 空 version 忽略。

仅允许每个 `(service, environment)` 的最新一条从 `in_progress` 改为 `success`：窗口内只剩该 version，或窗口内已无该服务活动且距 `deployed_at` 超过 30 分钟。历史事件不可变。`reported` 行不由推断逻辑改写。

推断事件保留 90 天；超期删除。失败不得阻断目录发现；记录异常则让对账任务按现有重试策略失败（目录 `discover` 幂等）。

## 读取

首页 `_build_releases` 只读 `ApmDeploymentEvent`：当前组织、未归档服务、近 7 天、按 `deployed_at` 倒序最多 5 条。不再调用 `deployment_releases()`。

## 回填

运行期命令 `apm_backfill_deployment_events` 调用现有 7 天 `deployment_releases()`，把缺失的推断事件写入表；已存在的 `(service, environment, version, inferred)` 只允许把 `deployed_at` 前移到更早的首次出现。不加入 `batch_init`，VictoriaTraces 失败不得阻塞启动。

## 验收

- 同一 version 连续对账不产生重复事件。
- 版本升高且新旧共存 → 最新事件 `in_progress`；旧版本离开窗口后收敛为 `success`。
- 版本号回退且旧 version 已离开窗口 → `rollback`。
- 首页发布段在有表数据时展示，且不依赖本次请求的 VictoriaTraces 发布聚合。
- 跨组织不可见。
- `batch_init` 不含回填命令或新对账任务。
