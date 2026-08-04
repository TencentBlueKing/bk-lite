# Incident IM 群验证入口（兼容旧链接）

原飞书单平台 Runbook 已被双平台验收合同替代。

请使用：[Incident IM 飞书/企业微信完整链路 Runbook](./incident-im-group-dual-platform-runbook.md)。

旧版中的“停止后重新创建”“解绑后换平台”和 `active_slot` 均不是当前产品语义：
一个 Incident 只能创建一次协作群；创建前可从多个平台中选择一个渠道，创建后不可切换；
“停止管理”保留外部群和不可变绑定，也不允许再次创建。
