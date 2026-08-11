# Stargazer 无状态异步采集：完整新方案（产品锁定）

更新日期：2026-08-06  
变更目录：`specs/changes/stargazer-stateless-async-collection/`  
权威细节：同目录 `spec.md`（本文是走读锁定后的执行总览）

Status: **approved for implementation**

## 1. 一句话

Sanic 统一异步采集运行时：薄租约去重、有界目标并发、TargetPolicy + CredentialAttempt、
单目标即推、失败等下周期；同步 SDK 允许插件内 `to_thread` 包装。

## 2. 调用方事实

- Telegraf / CMDB 配置采集使用**固定** `task_id`（`CollectModels.id` / `collect_task_id`）
- CMDB `execution_id` 与 Stargazer `task_id` 不是同一概念；失败不靠同 ID 断点续跑
- 主路径：采集 → VM → CMDB 拉指标对账；配置文件另有 NATS 回调
- Pod 丢单可接受；已发布结果保留；下周期整轮补采

## 3. 架构锁定

```text
HTTP Ingress
  → CollectionRequest
  → 薄租约 SET NX+TTL（执行中 → 202 skip）+ 本 Pod 容量（满 → 429）
  → app.add_task(CollectionRun)
  → 有界 TargetExecutor
       → TargetPolicy（出站；TCP 短探；SNMP/UDP 不做假可达）
       → CredentialPolicy（串行 / 亲和 / S1 冷冻）
       → CredentialAttempt（结构化结果；插件可选内部廉价检查）
       → 单目标立即发布（失败再试 1 次）
```

### 不做

- digest `409`、fencing 接管、pending/checkpoint 同 task_id 续跑
- 强制公开 `AccessProbe` / 默认 `UNKNOWN → 采集` 主路径
- ARQ / 专用同步插件线程池 / 通用 Session 框架
- ICMP 硬过滤；裸 UDP 当 SNMP 可达
- 测试双轨（旧续跑语义测试删除或改写）

### 异步边界

- 全链路异步编排
- 无异步能力的 SDK：插件内 `asyncio.to_thread` + **真实 SDK timeout**（允许）
- `async def` 内直接阻塞：禁止（契约心跳测试挡住）

## 4. 凭据与 Attempt

| 项 | 锁定 |
| --- | --- |
| 冷冻梯度 S1 | `5min → 30min → 4h → 24h` + 抖动 |
| 成功 | 只清当前凭据失败 + 亲和 |
| `capability_denied` | 暂同 `auth_rejected` |
| `protocol_no_response` | 不冻；默认连续最多 3（可配置取消） |
| `auth_rejected` | 继续试完未冷冻凭据 |
| 本变更必做协议 | **SNMP（优先）、host、VMware（配置+monitor 同一套）** |
| 云 | API Endpoint TCP/TLS（非 ping）；做不了身份检查则不做假探针 |
| host | monitor host remote + 配置 SSH/Job；到目标 Attempt 以 Responder 为准；保留回调 token |

## 5. 发布

- 单目标完成立即推送
- 去掉 pending/fencing 续跑路径
- 发布失败再重试 **1** 次（共 2 次），仍失败则目标失败

## 6. 另开任务（不阻塞本实现）

- Stargazer ↔ CMDB 凭据事件字段对齐
- CMDB「VM 查询 → 转换层 → 图库」排查
- 其余厂商协议 Attempt 分批
- 自适应扇出/半开（评审提案，未批准为本变更必做）

## 7. 实施顺序（代码）

1. 薄租约 + 删除/改写 fencing·pending 续跑测试与实现；发布重试 1 次
2. S1 冷冻 + 成功只清当前 + 无响应连续上限 3
3. 运行时 CredentialAttempt 决策（去 UNKNOWN 主路径）
4. SNMP Attempt（最小 GET）+ 256 混合真实链路测试与报告
5. host Attempt 契约（SSH/Job + monitor remote）
6. VMware Attempt（配置 + monitor）
7. 固定测试集新鲜跑通；保证通过率；更新 spec 证据

## 8. 测试锁定

- TDD；不双轨
- 固定命令见 `spec.md` §测试方案 §8
- 真实 SNMP 256：`10.10.69.0–255`，外层超时 5s；真实目标凭据**仅环境变量注入**，不得入库
- 输出完整耗时/资源占用报告到本目录

## 9. 真实 SNMP 测试凭据注入（本地）

```bash
export STARGAZER_SNMP_TEST_PREFIX=10.10.69
export STARGAZER_SNMP_REAL_TARGETS_JSON='[...]'  # 含 host/version/community/snmp_port，勿提交
```

## 10. 实现进度（2026-08-06 晚）

已完成：

- 完整方案文档本文件 + `spec.md` 产品锁定
- S1 冷冻 `5m→30m→4h→24h`；成功只清当前凭据失败
- `protocol_no_response` 默认连续上限 3（可配置）
- 发布失败再试 1 次；删除 pending 续跑 e2e 门禁（不双轨）
- SNMP `probe()` 最小 GET（`to_thread`）+ 单元测试
- **薄租约完全收敛**：无 digest `409` / fencing 接管 / completed 回读；结束后 DEL；下周期 ACCEPTED
- **CredentialAttempt**：无 probe → `NOT_SUPPORTED` → 直接 collect；去掉 UNKNOWN 主路径
- **host Attempt**：配置 SSH/Job 保留 `script_executor.probe`；monitor host 返回 `NOT_SUPPORTED`（Responder 裁决）
- **VMware Attempt**：配置 `VmwareManage.probe` + monitor `VmwareCollector.probe`
- 固定套件与冲突/续跑测试已改写为薄租约语义
- SNMP 256 混合真实链路：见 `snmp-256-mixed-real-load-test-report-2026-08-06.md`（旧：4 超时）与 `snmp-256-mixed-real-load-test-report-2026-08-07.md`（新：**3 通 / 1 不通(.246)**，墙钟 ~10.2s）
- 主机采集 150 mock 压测：见 `host-150-mock-load-test-report-2026-08-07.md`（`10.10.41.0–149`，墙钟 ~5.2s，peak IO 150）
- 相关固定套件（不含长 SNMP 压测）：**99 passed**

待复测：

- `10.10.69.246` 单独连通性仍失败（community/ACL/网络），需在设备侧排查
- 主机 `10.10.41.0–149` 真实 SSH/Responder 可达性（本压测为全 mock）
