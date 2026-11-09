# 01 — RUM 分析可用性只看 VictoriaLogs

Status: ready

Blocked by: None

**What to build:** VictoriaLogs 可用、VictoriaTraces 不可用或未配置时，RUM 的会话、错误、页面、概览、告警
读数照常工作；接入健康单独展示 VictoriaTraces 的状态。

- [ ] 分析客户端探活只探 VictoriaLogs；构造与 `open()` 不再要求 VictoriaTraces 地址
- [ ] `_build_analytics()` 仅在 VictoriaLogs 地址为空时返回不可用；“logs 有、traces 空”时可用
- [ ] `probe_pipeline_health` 的分析已配置/可用只看 VictoriaLogs；VictoriaTraces 健康作为独立字段返回，
      meta / health 接口与前端读取该字段的地方保持兼容（字段只增不删）
- [ ] 受影响的测试夹具调整（验证报告 V2.5 清单），新增“logs 有、traces 空 → 可用”和
      “traces 健康独立呈现”的测试
- [ ] `server/apps/rum/tests` 在 sqlite 下全部通过

## Notes

- 只改可用性判断，不改任何 LogsQL。
- 网关写 VictoriaTraces 的链路不受影响。
