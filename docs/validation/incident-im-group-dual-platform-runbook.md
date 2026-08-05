# Incident IM 飞书/企业微信完整链路 Runbook

- 适用版本：企业版
- 平台：飞书、企业微信自建应用
- 数据要求：仅使用专用测试租户、测试企业、测试应用和测试人员
- 设计基线：[企业版 Incident 一键拉群完整设计](../superpowers/specs/2026-07-30-enterprise-incident-im-group-design.md)

## 1. 验收边界

验证同一套企业版 Alerts 状态机可通过 `system_mgmt` 的通用 `im_group` capability
驱动飞书或企业微信。创建前可选择任一 ready 渠道；创建后平台和渠道冻结。一个
Incident 终身只有一条绑定，停止管理后保留外部群且不能重新创建。

成员集合为 `operator + collaborators`，只增不减。新增成员可持续入群，从 Incident
移除成员不会被踢出外部群。Incident 关闭暂停、重开恢复；手工暂停和关闭持续同步是
不同操作。

## 2. 环境与安全检查

共同条件：

- 企业许可有效，企业构建已安装 `alerts_enterprise`；
- `WEB_BASE_URL` 可从两端客户端访问；
- 准备两名已映射负责人、一名已映射协作人、一名未映射协作人；
- 凭据只通过系统管理 UI 注入，不写入命令、截图、日志或本文；
- 记录时只保留 Incident ID、binding ID、脱敏 chat ID 尾号和平台 request ID。

飞书：

- 应用已启用机器人；
- 应用具备群创建、群查询、加人、发群消息和应用自管理相关权限；
- 通道映射最终可解析 `open_id`；
- `im_notification`、`im_group` capability 均为 ready。

企业微信：

- 使用企业内部自建应用，不使用微信开放平台 OAuth 应用；
- 应用可见范围包含根部门；
- 通道映射最终可解析企业内部 `userid`；
- 至少两名已映射成员，群主包含在初始成员中；
- `im_notification`、`im_group` capability 均为 ready。

## 3. 自动化门禁

发布候选必须先通过：

1. Feishu/WeCom Adapter 合同：约束描述、就绪诊断、建群、查群、增员、发消息、
   错误归一化和日志脱敏。
2. 企业 Alerts 合同：权限、不可变绑定、成员快照、Outbox fencing、ACK 丢失、
   分批、暂停、关闭/重开、许可失效和停止管理。
3. API/前端合同：Options 返回平台约束与 blocker；前端在不满足企业微信两人下限等
   条件时禁止提交。
4. 数据库：`alerts_enterprise` 只有 `0001_initial`，`makemigrations --check`
   无漂移，并能为 PostgreSQL、MySQL、SQLite 生成标准 ORM migration SQL。

## 4. 双平台逐项场景

以下场景分别在飞书和企业微信执行，并保存“BK-Lite 页面状态 + 客户端事实 +
服务端 request ID”三类证据。

1. 用户同步后，Options 只展示当前用户可用且 ready 的渠道，并正确列出映射、未映射、
   冲突、可选群主和平台 blocker。
2. operator 创建群；非 operator（包括超级管理员）被拒绝。初始群名、群主、成员和
   Incident 摘要正确。
3. 部分成员未映射不阻断其他成员建群；绑定显示 `active_partial`，补齐映射后自动入群。
4. 新增协作人自动入群；移除协作人不退群；同一用户不会因周期对账重复邀请。
5. 51 人按 50+1 串行处理；暂停或关闭发生在首批后时，不再调用第二批。
6. Incident 关闭暂停，重开按原配置续跑；手工暂停只有 operator 可恢复；关闭持续同步
   后只停止自动增员。
7. 模拟限流、网络超时和权限错误：可重试错误指数退避，永久错误停止盲重试，成员和群
   状态可行动。
8. 外部群被删除后，本地变为 degraded；重试只查询原群，不创建第二个群。
9. 企业许可在 Outbox 排队后失效：create/add/summary 均不得调用平台，绑定进入
   `license_invalid` 暂停；读接口、暂停、停止管理仍可用。许可恢复后由 operator 恢复。
10. 停止管理需输入完整群名；外部群保留，旧任务不再外呼，同一 Incident 再次创建始终
    返回冲突。

## 5. 平台专项故障注入

飞书：

- 重放相同 create UUID，只产生一个群；
- 重放相同 summary UUID，只产生一条摘要；
- 验证超过 50 人的分批及 `invalid_id_list` 部分成功语义。

企业微信：

- 首次 `appchat/get` 明确返回群不存在后才允许 `appchat/create`；
- 模拟 create 已成功但本地 ACK 丢失，重放时 `GET` 找到确定性 `chatid`，不得再次
  create；
- `GET` 超时、权限不足或返回不确定错误时不得 create；
- 建群后首条摘要必须成功，客户端才将群视为可用；
- 根部门可见性不满足时 capability 不能进入 ready；
- 外部联系人、微信客户和其他企业成员明确标记为不支持，不进入无限重试。

## 6. 阻断条件与清理

任一情况都阻断发布：重复群、错误平台/渠道、已移除人员仍被新拉入、暂停后继续外呼、
旧 worker 覆盖新终态、永久错误无限重试、许可失效仍产生外部副作用、凭据或完整外部
身份泄漏。

清理时先在 BK-Lite 停止管理，再由平台群管理员手工解散测试群；产品不会自动解散群。
证据归档前脱敏手机号、邮箱、外部用户 ID、token、secret 和完整 chat ID。
