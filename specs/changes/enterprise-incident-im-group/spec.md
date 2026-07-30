# 企业版 Incident 一键拉群

## Intent

企业版 Incident 负责人可在建群前从多个具备 `im_group` 能力的 IM 通道中选择一个，
为当前 Incident 创建唯一且不可切换的外部协作群，并可选择是否持续把后续新增的
Incident 当前期望成员补充进群。

本期真实验证平台为飞书和企业微信；其他 IM 在各自 Provider 和用户映射能力完成后
接入相同的 Alerts 企业版状态机。

## Locked decisions

- 功能仅属于企业版；社区版只保留通用扩展 seam。
- 企业源码归属 Git 子模块 `enterprise/server/apps/alerts_enterprise`；企业
  `registry_hooks` 把生命周期、Outbox 和 URL patterns 注册进社区 Alerts seam。
- 企业 app 不提供 `urls.py`，避免暴露 `/api/v1/alerts_enterprise/`；接口保持在
  `/api/v1/alerts/`。
- 本次不调整 `system_mgmt` 的代码结构和数据模型；复用现有 `wecom` Provider、用户
  同步和通知渠道，仅在既有 manifest/adapter 增加 `im_group`。
- 一个 Incident 生命周期内最多一个群绑定。
- Provider、channel 和 member ID 类型只在创建前选择，创建后不可切换。
- 停止管理为不可逆终态，不释放重新建群资格。
- 持续同步只增不减。
- 任意 Incident 负责人可以管理，协作人不能管理。
- 数据模型和迁移属于 `alerts_enterprise`，只提供一个 `0001_initial`。
- 企业前端复用 `prepare-enterprise.mjs` 的 `(enterprise)` junction/fallback。
- 真实租户闭环同时覆盖飞书和企业微信。

## Full design

完整的产品、CE/EE 架构、数据模型、状态机、HTTP Interface、前端交互、安全、
TDD 纵向切片、发布和迁移设计见：

[企业版 Incident 一键拉群完整设计](../../../docs/superpowers/specs/2026-07-30-enterprise-incident-im-group-design.md)

## Superseded assumptions

以下旧假设不再有效：

- 具体 IM 群业务直接实现于社区版 `alerts`；
- 社区版 Alerts 持有 Incident IM 数据表和迁移；
- 首次设计只把飞书作为产品名称而不是首个 Provider；
- 停止管理后可以重新选择通道或平台建群；
- 使用 `(incident, active_slot)` 为重新建群释放唯一槽位。

## Verification seams

1. 社区版无企业包降级。
2. Incident Extension Interface。
3. Outbox Handler Registry Interface。
4. 企业 HTTP Interface。
5. IncidentIMChannelGateway Interface。
6. 群领域与 Delivery Interface。
7. Incident 生命周期与周期补偿。
8. 企业 Web 用户 Interface。
9. 企业许可 fail-closed。
10. 真实飞书、企业微信测试租户 Runbook。
