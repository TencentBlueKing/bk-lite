# 监控 / 日志 / APM 告警处理人与分派——实施计划

Status: complete

Date: 2026-09-09

规格：[spec.md](./spec.md)

## 1. 目标

给监控、日志、APM 的领域告警补上策略默认处理人、告警处理人快照、「我的告警」过滤，以及空处理人活跃告警的认领 / 分派 / 关闭。手工分派按策略通知配置发给被分派人。

本期不写事件表、不做事件页。认领 / 分派必须落在单一服务入口，供 614 后续接事件写入。

## 2. 本版本范围

### 2.1 包含

- APM 策略补所属组织（本 app 内实现，参考日志 `PolicyOrganization` / 监控策略组织，不复用监控表）。
- 三域策略、告警增加 `handlers`。
- 创建告警时快照策略处理人。
- 策略表单：处理人多选；通知人默认带处理人，可删。
- 告警列表：列名「处理人」展示 `handlers`；`my_alert` 过滤。
- 空处理人的活跃告警：认领、分派、关闭。
- 分派选人 = 告警所属组织中的未禁用用户。
- 手工分派通知（仅需接收人的人工渠道）。
- 改写三域 capability 中「不做分派」的过时边界。

### 2.2 不包含

- 614 事件写入与事件页。
- 转派、认领通知、创建当分派。
- 历史回填、告警中心回写、OpenAPI。

## 3. 数据契约

### 3.1 字段

| 对象 | 字段 | 含义 |
|---|---|---|
| 策略 | `handlers` JSON 列表，默认 `[]` | 新告警默认处理人 |
| 告警 | `handlers` JSON 列表，默认 `[]` | 当前处理人快照 |
| 告警 | `operator` | 仍为关闭 / 恢复操作人，不在列表当处理人展示 |

监控：`MonitorPolicy` / `MonitorAlert`。  
日志：`Policy` / `Alert`。  
APM：`ApmPolicy` / `ApmAlert`（APM 策略没有扁平 `notice_users`，处理人只放策略字段）。

标识与通知人下拉的 `value` 一致（当前为用户 `id`）。匹配时同时认 id 与 username。

### 3.2 状态与动作

告警状态机不改。新增的是处理人是否为空：

| 告警状态 | `handlers` | 可做 |
|---|---|---|
| 活跃（监控/日志 `new`，APM `active`） | 空 | 认领、分派、关闭 |
| 活跃 | 非空 | 关闭 |
| 恢复 / 关闭 | 任意 | 不可认领、不可分派 |

认领：`handlers = [当前用户标识]`。  
分派：`handlers = 请求名单`（去重、至少一人）。  
创建快照：`handlers = list(policy.handlers or [])`。

### 3.3 API

各域在现有告警资源上增加：

- 列表查询：`my_alert=1`，在已有可见集合上再筛处理人包含当前用户。
- `POST .../claim/`：无 body。
- `POST .../assign/`：`{"handlers": ["..."]}`。
- 分派选人：监控 / 日志复用 `user_all?organization_ids=`；APM 在本域补同等接口，不能调用监控 / 日志，也不能只用当前组织的接收人搜索。

关闭接口不变。认领 / 分派权限与该域关闭相同。

分派校验失败返回 400；看不见或无操作权限 403；已有处理人或非活跃 409。

## 4. 后端切片

### T0 APM 策略所属组织（613 的 APM 前置）

- `ApmPolicyOrganization`（policy + organization，唯一），读写字段对外仍用 `organizations` 列表，与监控 / 日志表单一致。
- 创建必填；`validate_assignable_organizations`。更新时只有显式传入才改组织。
- 策略列表 / 详情从 `service__organization_links` 改为策略自己的组织过滤。
- 迁移：已有策略从 `service.organization_links` 回填。回填后仍无组织的策略按 fail-closed 不可见，不另做超管修补接口。
- `DjangoApmPolicyService` 新建 Alert / Event 时改读策略组织。已有 Alert 不改写。
- 策略编辑页增加必选组织树，选服务且组织为空时带入服务组织。
- 改 `apm-alerting.md`：生成时快照从服务组织改为策略组织；策略组织变更不影响已有告警。

### T1 模型与序列化

- 三域 migration：策略、告警各加 `handlers`。
- 策略 / 告警序列化显式暴露 `handlers`。监控策略若仍 `__all__`，本切片只保证字段出现，不借机重写全部字段清单。
- 列表补充 `handlers_display`，复用通知人展示名解析。

### T2 创建快照

- 监控：`EventAlertManager._create_new_alerts` 写入 `handlers=list(self.policy.handlers or [])`。
- 日志：`LogPolicyScan` 建 Alert 时同样快照。
- APM：`DjangoApmPolicyService` 新建 Alert 时快照 `policy.handlers`；已有 Alert 不改 `handlers`。
- 无数据 / 缺失检测等所有新建 Alert 入口必须走同一快照，禁止漏拷。

### T3 认领 / 分派服务

每域在本 app 内自建服务，语义对齐，代码不互相 import，也不抽到 `apps.core`：

1. `select_for_update` 读告警。
2. 校验可见 + Operate、活跃、`handlers` 为空。
3. 认领写入当前用户标识；分派校验用户存在、未禁用、属于告警 `organizations`。
4. 条件更新 `handlers`。
5. 分派成功后，监控 / 日志在策略仍存在且 `notice` 为开时 `on_commit` 发分派通知；APM 在仍有可对人渠道时发。策略已删除则跳过。

614 只允许挂在这个成功点之后，本期不调用事件写入。

### T4 列表过滤

- `my_alert` 用现有 `build_json_membership_query`，传入当前用户 id 与 username。
- 过滤叠在现有组织可见性之后，不得放大可见范围。

### T5 分派通知

- 监控：`AlertLifecycleNotifier` 增加 `assigned`，接收人 = 本次 `handlers`，渠道仍用告警 / 策略已选渠道。不投告警中心副本当成分派通知。仅 NATS 或无需接收人的渠道跳过。
- 日志：对等；非告警中心渠道把接收人换成 `handlers`。
- APM：对 `delivery_mode=message` 且需要系统用户的 target 建 outbox，`recipients=handlers`。`recipient_mode=none` 或告警中心副本不发。分派选人与策略处理人候选走本域按组织取用户接口，不复用当前组织接收人搜索。

### T6 策略表单后端校验

- 监控 / 日志：策略处理人必须是策略组织内未禁用用户。
- APM：策略处理人必须是该策略所属组织内未禁用用户。
- 组织变更后的越界处理人拒绝或由前端剔除后提交；后端仍二次校验。

## 5. 前端切片

### T7 策略配置

- 监控 / 日志 `notificationForm`：处理人多选，候选 = 现有 `getAllUsers(策略组织)`。
- 开启通知且出现通知人表单项时：若通知人为空且处理人非空，写入处理人；之后用户删除不自动补。
- 组织变更：处理人与通知人一并按候选剔除。
- APM `policy-editor`：先有策略组织，再有处理人；处理人候选来自策略组织。系统用户接收人空且已有处理人时默认带入。
- 监控模板批量套用带 `handlers: []`。

### T8 告警列表与详情

- 活跃 / 历史列表「操作员」文案改为「处理人」，绑定 `handlers` / `handlers_display`。
- 增加「我的告警」开关或勾选，请求带 `my_alert=1`。只改查询，不改权限。
- 活跃且 `handlers` 为空：认领、分派、关闭。有处理人或非活跃：关闭规则与今天一致。
- 分派弹层：多选，选项来自告警所属组织用户接口。
- 详情同样展示处理人，并提供上述操作。

## 6. 614 接缝

认领 / 分派事件写入见 `specs/changes/domain-alert-lifecycle-events/spec.md`。本切片已预留且必须保持：

- 认领 / 分派成功后的唯一扩展点在 T3 服务；614 在同一事务内写事件。
- 监控 `MonitorEvent` 对 `triggered/recovered/closed` 的「每告警每动作一条」约束**不要**扩到认领 / 分派。
- 日志 Event 的 `action`、关闭补写、详情时间线由 614 做，613 不改日志 Event 模型。
- 监控 / APM 关闭 / 恢复继续走现有路径，614 不得再插一条。

## 7. 测试切片

沿用各域现有策略、扫描建警、告警 ViewSet、关闭、通知测试，补：

| 编号 | 行为 |
|---|---|
| C1 | 策略保存处理人；越界用户 400 |
| C2 | 新建告警 `handlers` 等于当时策略；随后改策略旧告警不变 |
| C3 | 空处理人活跃告警认领成功；第二次认领 409 |
| C4 | 分派给告警组织内用户成功；组织外 / 禁用 400 |
| C5 | 有处理人后认领 / 分派 409；关闭仍成功 |
| C6 | 非活跃不可认领 / 分派 |
| C7 | `my_alert=1` 只出处理人匹配当前用户的可见告警；`operator` 是自己但 `handlers` 为空不出 |
| C8 | 分派 + 通知开启 → 接收人是被分派人 |
| C9 | 分派 + 通知关闭 → 不发 |
| C10 | 创建告警不发分派通知 |
| C11 | 前端：空处理人三按钮；有处理人无认领 / 分派；我的告警带参；通知人默认带处理人可删 |
| C12 | APM 策略无组织创建失败；列表只出策略组织命中当前组织的策略 |
| C13 | APM 新告警 `organizations` 等于当时策略组织；改服务组织后旧策略与旧告警不变 |
| C14 | 策略已删除时仍可认领空单，分派通知不发 |

验证命令（实现时按实际测试文件替换）：

```text
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/monitor/tests apps/log/tests apps/apm/tests --no-cov -k "handler or assign or claim or my_alert"
cd web && pnpm test 中与策略表单、告警列表相关的目标
```

## 完成证据

- T0：`apps/apm/tests` 386 passed；APM 策略组织 API / 快照 / 编辑页已落地。
- T1：三域策略、告警增加 `handlers`；列表补 `handlers_display`。`apps/monitor/tests/test_alert_handlers.py`、`apps/log/tests/test_alert_handlers.py`、`test_policy_api.py::test_policy_create_persists_handlers`、`test_alert_snapshot_api.py::test_alert_list_exposes_handlers_and_display` 通过。
- T2：新建告警快照当时策略 `handlers`，已有告警不改写。监控 / 日志扫描与 APM evaluate 的 C2 用例通过。
- T3：三域各自认领 / 分派服务与 `POST .../claim/`、`POST .../assign/`。C3 空单认领后第二次 409；C4 组织内用户可分派、组织外 / 禁用 / 不存在 400；C5 有处理人后认领 / 分派 409、关闭仍成功；C6 非活跃 409；C14 策略已删除仍可认领空单，分派通知不发。不写事件表。
- T5：手工分派按策略已开的人工渠道发给本次 `handlers`。C8 接收人是被分派人而不是策略通知人；C9 通知关闭不发；C10 创建不发分派通知；告警中心副本 / 仅 NATS / `recipient_mode=none` 跳过。认领仍不发。
- T4：三域列表 `my_alert=1` 在组织可见集合上再筛 `handlers` 含当前用户 id 或 username。C7：处理人匹配才出，`operator` 是自己但处理人为空不出，组织外告警仍不可见。
- T6：策略保存处理人须为策略组织内未禁用用户。C1：组织内用户可保存；组织外 / 禁用 / 不存在 400；组织变更后越界处理人 400。
- T7：三域策略表单可配置处理人；候选来自策略组织。监控 / 日志通知人空且处理人非空时默认带入，删除后不补；组织变更一并剔除越界处理人与通知人。APM 处理人在所属组织之后，系统用户接收人同样默认带入。监控模板批量套用强制 `handlers: []`。APM 本域 `notification-recipients/?organization_ids=` 按策略组织取用户。
- T8：三域告警列表 / 详情列名改为「处理人」并绑定 `handlers` / `handlers_display`。「我的告警」请求带 `my_alert=1`。空处理人活跃告警展示认领、分派、关闭；有处理人后无认领 / 分派。分派弹层多选告警所属组织用户；APM 复用本域 `organization_ids` 接收人接口。C11 前端用例与 `event-user-display-test.ts` 通过。

## 8. 发布与回滚

APM 策略组织（T0）与 `handlers` 读接口先于按钮发布。回滚前端即可关掉新按钮和新组织表单项；`handlers` 与策略组织表可空保留。不得在回滚时删已写入的处理人或策略组织。
