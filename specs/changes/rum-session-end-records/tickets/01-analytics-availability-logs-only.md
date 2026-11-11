# 01 — RUM 分析可用性只看 VictoriaLogs

Status: done

Blocked by: None

**What to build:** VictoriaLogs 可用、VictoriaTraces 不可用或未配置时，RUM 的会话、错误、页面、概览、告警
读数照常工作；接入健康单独展示 VictoriaTraces 的状态。

- [x] 分析客户端探活只探 VictoriaLogs；构造与 `open()` 不再要求 VictoriaTraces 地址
- [x] `_build_analytics()` 仅在 VictoriaLogs 地址为空时返回不可用；“logs 有、traces 空”时可用
- [x] `probe_pipeline_health` 的分析已配置/可用只看 VictoriaLogs；VictoriaTraces 健康作为独立字段返回，
      meta / health 接口与前端读取该字段的地方保持兼容（字段只增不删）
- [x] 受影响的测试夹具调整（验证报告 V2.5 清单），新增“logs 有、traces 空 → 可用”和
      “traces 健康独立呈现”的测试
- [x] `server/apps/rum/tests` 在 sqlite 下全部通过

## Notes

- 只改可用性判断，不改任何 LogsQL。
- 网关写 VictoriaTraces 的链路不受影响。

## Completion evidence

- 分析探活与 `VictoriaAnalytics.open()` 只接收 VictoriaLogs 地址；`_build_analytics()` 在 logs 地址为空时返回不可用，logs 有、traces 空时会话读取仍可用。
- `probe_pipeline_health` 的 `analyticsConfigured` / `analyticsAvailable` 只看 VictoriaLogs。接入健康新增 `tracesConfigured`、`tracesAvailable`，不可达时另加 `tracesUnavailable`。原有字段保留。
- 指定命令在本机未进入用例：`server/.env` 的 `INSTALL_APPS` 含 `monitor` 不含 `cmdb`，Django 启动即失败：`RuntimeError: Model class apps.cmdb.models.auto_relation_pending.AutoRelationPending doesn't declare an explicit app_label and isn't in an application in INSTALLED_APPS.`
- 补上 `cmdb` 后，sqlite 迁移失败（与本任务无关）：`django.core.exceptions.FieldDoesNotExist: NewApmIngestSourceOrganization has no field named 'ingest_source'`。当时 85 passed，110 errors。
- 通过的命令（195 passed，约 8.3s）：

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb \
  uv run pytest apps/rum/tests --no-cov --nomigrations -o addopts=
```

- 没有改 `web/`。`/meta` 与 `/health` 只增加字段，现有读取保持原样。本机 `pnpm type-check` 在 `build:isoflow` 因缺少 `webpack` 无法启动，因此没有把可选类型写进前端。
- 复核修正：`/meta` 不再同步探活 VictoriaTraces（只返回 `tracesConfigured`），避免接入页在 VictoriaTraces 不通时等待；`/health` 保留探活，超时上限 3 秒。复跑同一命令 196 passed。
