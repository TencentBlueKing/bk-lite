# 告警源权限与凭据接口收口

## 背景

Issue #4116 指出告警源默认 CRUD 与接入指南仅受登录校验保护。当前产品权限资源只定义
`Integration-View` 和 `Integration-Detail`，集成页面实际提供告警源查询、接入指南和组织
密钥管理，不提供通用告警源增删改能力。

告警筛选、告警分派、屏蔽策略、告警丰富、相关性规则和动作规则仍需要读取告警源选项，
但这些调用方不应获得告警源配置或凭据。

## 权限与响应契约

| Interface | 权限 | 契约 |
|---|---|---|
| `GET alert_source/options/` | 已知调用页面任一 View 权限 | 仅返回 `id/name/source_id/source_type` |
| `GET alert_source/` | `Integration-View` | 返回集成概览，不含 `config/secret/team_secrets` |
| `GET alert_source/{id}/` | `Integration-Detail` | 返回显式详情字段和安全配置投影 |
| `GET alert_source/{id}/integration-guide/` | `Integration-Detail` | 返回带 `{{TEAM_SECRET}}` 占位符的模板，不返回真实凭据 |
| `POST alert_source/{id}/integration-material/` | `Integration-Detail` + 组织归属 | 只为指定组织生成带凭据材料 |
| 组织密钥列表/新增/轮换/删除/查看 | `Integration-Detail` + 组织归属 | 列表不返回明文；敏感动作只处理一个组织 |
| 默认 POST/PUT/PATCH/DELETE | 不开放 | 返回 405 |

options 的允许权限为 `Integration-View`、`Alarms-View`、`alert_assign-View`、
`shield_strategy-View`、`alert_enrichment-View`、`correlation_rules-View` 和
`action_rules-View` 的并集。options 之外的告警源接口不得复用该权限并集。

## 配置投影

告警源 serializer 必须显式列字段，禁止 `fields = "__all__"`。概览不返回 `config`；
详情只返回 allowlist 配置。`auth/password/token/secret/secret_key/api_key/authorization/cookie`
等敏感键必须递归剔除，任何配置字符串中的源级或组织密钥必须替换为
`{{TEAM_SECRET}}`。

## 组织密钥不变量

- 非超级用户只能操作 `request.user.group_list` 内的组织；跨组织请求返回 403。
- 超级用户可操作任意组织。
- 列表只返回调用者可管理组织的元数据，不批量返回明文密钥。
- 新增、轮换、查看和生成材料每次只返回目标组织的一份凭据。
- 所有 JSON 映射写入必须在 `transaction.atomic()` 和 `select_for_update()` 内完成。
- 日志只记录稳定 action、actor、source_id、team_id 和终态，不记录凭据或响应正文。
- SNMP Trap 不支持组织密钥；其默认组织部署材料是唯一允许使用源级密钥的受控例外。

## 迁移与回滚

先增加 options、受控凭据和 material Interface，再迁移 Web 调用，最后裁剪旧 list/detail/guide
响应。回滚只能回退新调用方或展示逻辑，不得重新开放默认 CRUD、全量配置响应或无权限 guide。

## 验收

- 无 Integration 权限的认证用户不能访问管理查询、指南或凭据动作。
- 页面专属 View 角色可访问 options，但不能访问管理详情。
- `Integration-View` 不能读取详情、指南或凭据；`Integration-Detail` 只能操作授权组织。
- list/options/detail/guide 不包含敏感哨兵；material 只包含目标组织凭据。
- 跨组织操作返回 403 且数据库不变；并发组织密钥写入不会丢失更新。
- API Token 与网页登录遵守相同权限矩阵；默认写方法保持 405。
