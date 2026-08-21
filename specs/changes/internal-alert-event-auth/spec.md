# 内部告警事件组织归属认证

Status: implemented

## Problem Statement

告警中心历史上仅凭 NATS 消息里的 `pusher` 字符串信任事件自报的 `organizations`，已登记告警源以外的调用者可伪造内部来源并把事件写入任意组织。该边界同时存在旧生产者、旧接收者和滚动发布，不能用一次性拒绝旧协议的方式修复。

## Solution

- `lite-monitor`、`lite-log`、`lite-apm`、`lite-patch` 的内部组织事件使用 HMAC envelope；签名覆盖版本、RPC scope、真实 caller、时间戳和完整 payload。patch_mgmt 不复用 monitor 身份。
- system_mgmt 先验证 producer/caller，再把事件组织收敛到通知渠道授权组织；转发 alerts 时生成新的接收端签名。
- alerts 只在 caller、pusher、payload 和签名一致且时间窗有效时采信认证。携带但无效的签名始终拒绝，不得降级为旧协议。
- 每个 caller 优先使用自己的 current key，接收者按 caller 选择验证 key，并仅在 legacy 迁移期开启时同时接受全局 key/Django secret fallback。严格模式同时撤销无签名路径和共享 key fallback。previous key 仅用于验证，以覆盖有界轮换窗口。缺失 key 时签发失败、验证失败。
- 已登记的外部告警源保持既有 source secret 契约，不强制使用内部 caller envelope。

## Compatibility And Rollout

1. 首次发布保持 `ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH=true`。新接收者只对完全缺失 envelope 的旧内部生产者走 legacy，并记录告警；无效、篡改或过期 envelope 不允许降级。
2. 新代码显式迁移仓内 monitor、log、APM、patch_mgmt 调用方。旧 ACK token 继续提供逐事件确认与生命周期身份；不带组织提升的旧 ACK 在严格模式仍可工作，带 `organizations` 的 ACK 必须通过 HMAC。
3. 为每个 producer 仅下发自身的 `ALERTS_INTERNAL_EVENT_AUTH_<CALLER>_KEY`；receiver 持有 caller 验证集合。完成 caller key 切换后移除 producer 的全局 fallback key。
4. 所有实例完成滚动升级且 legacy 日志归零后，部署侧设置 `ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH=false`，关闭伪造路径。该启用动作由部署 Issue #4900 跟踪。
5. caller key 轮换时先配置新 current key 和旧 previous key，待最长消息窗口与在途重试耗尽后移除 previous key。

回滚优先把 legacy 开关暂时恢复为 `true`，不回滚组织收敛和无效签名拒绝；若新 key 异常，则恢复旧 key 为 current。开关恢复只用于有界止血，部署子 Issue 必须继续跟踪严格模式收口。

## Runtime Contract

- 正常：RPC producer 签名经过 system_mgmt 验证，组织被渠道 team 收敛，alerts 验签后落库。
- 失败：caller/pusher 不一致、payload/组织篡改、签名过期、空 key、渠道越权以及 legacy 模式下的无效签名均稳定拒绝。
- 兼容：缺失签名的旧内部生产者仅在 legacy 开关开启时可用；显式关闭后拒绝。已登记外部 source 与无组织提升的旧 ACK 保持旧行为。
- 轮换：previous key 在窗口内可验证，current key 始终用于新签名。

## Out Of Scope

- 在本代码变更内直接修改生产部署环境变量。
- 为已登记外部告警源替换既有 source secret 认证模型。
