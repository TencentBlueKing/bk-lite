# APM / RUM 查询性能改造的遗留问题收口

Status: done

来源：`observability-aggregate-metrics`、`rum-session-end-records`、`apm-policy-merged-queries` 三份变更完成后的复核遗留。

## Problem Statement

三份变更已在分支 `feat/apm-rum-query-performance` 完成。复核时记下几处不属于原 ticket 范围、但会误导使用者或妨碍验收的问题：

1. APM 数据面端到端契约测试 `deploy/apm/tests/test_data_plane_contract.py` 已经跑不通。`999469c6b3`（2026-08-13）起，
   接入片段必须带探针下载地址，测试没有跟着更新。这个测试只在显式开启时运行，所以一直没人发现。
2. 可用性 SLO 回退到 VictoriaTraces 时，即使明细保留期短于 SLO 窗口（30 天、自然月），也照样给出达成率。
   缺失的旧数据会让达成率失真，页面却显示为可用。
3. RUM 告警详情的指标趋势把「无样本」画成 0。Web Vitals 的 0 毫秒看起来是“极好”，会误导判断。
4. 全仓 `pnpm lint` 有 3 个既有错误，`pnpm lint` 不能作为通过门槛。
5. 改造只做了单测和容器契约测试，没有在本机真实环境里接上聚合库、在浏览器里走查页面。

## Solution

逐项修复 1–4，再做一次本机全链路验证（5）。不改变三份变更已定的口径。

## Implementation Decisions

- 契约测试按当前接入片段契约补上探针下载地址；断言范围不变，不为让测试通过而放宽服务端校验。
- SLO 保留期判断只在 VictoriaTraces 回退路径上做：读 `APM_TRACE_RETENTION`（与健康检查同一解析函数），
  窗口长度超过保留期时，这条 SLO 的达成率为空，原因是“明细保留期不足”，不显示为 0。聚合库路径不受影响。
  延迟类 SLO 同样走 VictoriaTraces，适用同一判断。
- 告警详情趋势：服务端已有的空值保持为空，前端在空值处断开折线，悬停显示「—」。VictoriaLogs 回退路径原来就补 0，不改。
- lint：只修这 3 处既有错误，不顺带改其他文件。
- RUM 分布口径不改：国家、设备、环境、版本分布读原始事件，会话数 KPI 读会话结束记录，两者可能有细微差异。
  这已在 `rum-session-end-records` spec 的决定里写明（窗口内有事件的会话与窗口重叠的会话，两种口径基本一致），
  继续沿用。会话数、错误会话率告警窗口只有 5–60 分钟，读原始事件既准确又便宜，同样不改。
- 本机验证用临时聚合库容器（端口避开 8428、9428、10428）和 `deploy/local` 的 Make 目标启动应用进程。
  聚合数据用合成样本写入临时库，不改用户的明细库。

## Testing Decisions

- 1：开启 `RUN_APM_CONTAINER_CONTRACT=1` 后，`test_data_plane_contract.py` 全部通过；临时容器使用独立 project 名。
- 2：sqlite 下 `server/apps/apm/tests` 通过（已知基线 11 项 sqlite 失败）；补保留期短于窗口、等于窗口、
  聚合路径不受影响的测试。
- 3：相关 vitest、改动文件 eslint、`pnpm type-check`。
- 4：全仓 `pnpm lint` 退出码 0。
- 5：验证记录写进 ticket 的 Completion evidence，附截图路径。

## Out of Scope

- 聚合库的生产部署与运维流水线。
- RUM 分布与会话类告警改读会话结束记录。
- 本机 Docker 磁盘清理、`bklite-dev-minio` 重启和用户 APM 栈中 system collector 的 unhealthy 状态排查（最后一项在 05 中只做只读检查并报告）。
