# 企业版 Incident 一键拉群

Status: in-progress

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
- 群协作 Provider 使用内置平台接口，不向管理员暴露 URL 配置；能力检查是可选诊断，
  `capability_status.im_group` 不作为 Incident 渠道可选条件，也不要求为了诊断额外申请
  应用信息读取权限。
- 一个 Incident 生命周期内最多一个群绑定。
- 外部协作群名称固定使用创建时的事故名称 `Incident.title`；前端只读展示，后端忽略
  客户端自定义群名并保存事故名称快照。
- 建群成功后保存平台返回的 `external_chat_id` 作为外部群唯一标识；后续系统消息通过
  `provider_key + channel + external_chat_id` 路由，不解析群名。
- Provider、channel 和 member ID 类型只在创建前选择，创建后不可切换。
- 通道是运行期依赖而不是群绑定的生命周期所有者；通道删除后保留绑定及成员
  审计快照，实时引用置空，绑定进入不可重试的 `degraded` 状态且不再外呼。
  删除前已进入第三方平台的在途请求允许完成并记录已确认的外部事实，但不得覆盖
  `degraded / IM_CHANNEL_MISSING` 或派生新任务；删除被 Worker 观察后不得发起新请求。
- 停止管理为不可逆终态，不释放重新建群资格。
- 持续同步只增不减。
- 创建预览展示全部 Incident 当前期望成员，但只有所选通道下具有唯一有效映射的
  “可加入成员”会提交给 IM；待映射和映射冲突成员本次排除且不阻断建群。
- 非群主成员被平台判定无效时不得拖垮其他有效成员：飞书使用平台返回的无效 ID，
  企业微信由 Adapter 采用最小可用建群和有调用预算的成员隔离，最终收敛为
  `active_partial` 与成员级可行动错误。群主无效或平台最小成员条件不满足仍阻断创建。
- 企业微信单批隔离的 32 次调用预算包含预检群成员查询；部分成功后遇到可重试平台
  错误时，已确认事实先落库，未完成成员保持待处理并由 Outbox 重试。
- 企业微信创建预检对当前环境返回的 86001/86003 视为“群尚不存在”，随后使用同一
  确定性 `chatid` 创建；86008 表示其他应用占用，必须失败，不得继续创建。
- 任意 Incident 负责人可以管理，协作人不能管理。
- 数据模型和迁移属于 `alerts_enterprise`，只提供一个 `0001_initial`。
- 企业前端复用 `prepare-enterprise.mjs` 的 `(enterprise)` junction/fallback；junction
  源码通过生成的 `enterprise/web/node_modules -> web/node_modules` 链接复用主 Web 的
  唯一依赖树，不单独安装 React、Ant Design 等运行时依赖。
- 真实租户闭环同时覆盖飞书和企业微信。
- 建群、增员和摘要发送失败必须记录脱敏结构化日志，包含 Incident/群绑定、平台、
  通道快照、操作阶段、统一及第三方错误码、内部及第三方请求 ID；意外异常只记录
  异常类型，禁止记录外部账号、凭据和原始响应。

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
