# Historical Superpowers change: 2026-06-18-bot-usage-team-and-workflow-idor

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-18-bot-usage-team-and-workflow-idor-design.md

日期: 2026-06-18
状态: 已批准(经对话澄清),待实现后审查。**代码不合并 master,等审查。**

## 背景

opspilot 的 `Bot.team`(JSONField 组织 id 列表)是"管理组织":工作台可见、可编辑/删除/授权。
`execute_chat_flow` 目前也按 `team` 鉴权,即只有管理组织成员能对话。

需求:新增"使用组织"维度,使非管理组织也能"只对话",但不能管理。

## 已确认的需求边界

1. **使用组织 = 严格只对话、零查看**:只能调 `execute_chat_flow`,看不到任何对话历史/工作流执行结果(查看仍只归管理组织)。→ 与 IDOR 修复解耦。
2. **授权范围**:管理组织授权使用组织时,只能授权"授权人有权限的组织"(复用 `_validate_org_field_permission`)。
3. **鉴权入口**:只在 `execute_chat_flow` 强制(Web 用户 + API token);企微/钉钉/公众号渠道入口不纳入。
4. **不变式 `team ⊆ usage_team`**:新建 bot 时管理组织自动并入使用组织,且不可从使用组织删除 → 管理组织天然有使用权。
5. **测试入口(T2)**:`execute_chat_flow` 的 `is_test=True`(管理页测试)**额外要求 `current_team ∈ team`(管理组织)**;纯使用组织即使经 API 也不能触发测试(测试会回填管理画布、占"同 bot 同时仅一个测试"槽位)。

## 方案 A:平行字段 `usage_team`

### 数据模型
- `Bot.usage_team = JSONField(default=list)`,与 `team` 同构。
- 迁移 `0058`: `AddField` + `RunPython` 回填存量 bot `usage_team = team`(**必须**,否则统一查 usage_team 会让存量 bot 无人可对话)。回填后存量行为不变。

### 维持不变式 `team ⊆ usage_team`
- `BotViewSet.create`: `usage_team = list(team)`。
- `authorize_usage_team`(新 action): `usage_team = 去重(team + 请求传入)`,管理组织恒在、不可删;`_validate_org_field_permission` 只校验新增的非管理组织。
- `BotViewSet.update`: `team` 变更时把新 team 并入 `usage_team`。

### 授权接口
`POST bot_mgmt/bot/{id}/authorize_usage_team/`,body `{"usage_team": [...]}`。三重防护:
`get_object()`(team 作用域,非管理组织 404) + `get_has_permission`(管理编辑权) + `_validate_org_field_permission`(新增组织需有权限)。写操作日志。

### execute_chat_flow 鉴权(T2)
```
if is_test:
    team_filter = Q(team__contains=[current_team])              # 测试仅管理组织
else:
    team_filter = Q(usage_team__contains=[current_team])        # 对话:管理(含于usage)∪使用
    for gid in guest_group_ids: team_filter |= Q(team__contains=[gid])   # OpsPilotGuest 维持现状
bot_query = Bot.objects.filter(Q(id=bot_id) & team_filter)
if not is_test: bot_query = bot_query.filter(online=True)
```

### 序列化 / 管理面
- `BotSerializer` 加 `usage_team_name`(仿 `team_name`)。
- `usage_team` **不进 `UPDATABLE_FIELDS`**(只能经 create + authorize 改,防 mass-assignment)。
- list/编辑/删除/工作台可见 仍只认 `team`,不变。前端使用组织选择器:管理组织项勾选+置灰禁删。

## 工作流执行结果 IDOR 修复(两接口 + 一并收口)

`workflow_task_result_view.py` 的自定义 action 直接按裸 `execution_id` 查 `WorkFlowTaskNodeResult`,绕过 team 作用域。

**租户边界事实**:节点表 `WorkFlowTaskNodeResult` 无 team 字段,只能经同 `execution_id` 的 `WorkFlowTaskResult`(→ bot.team)判定归属。视图 `get_queryset()` 已做 team 过滤。

**修复**:新增 `_authorize_execution(request, execution_id, task_result_id)`:经 team 作用域 `get_queryset()` 解析 `WorkFlowTaskResult`;找不到(不存在/他团队)一律 `NotFound`(404,不区分,防枚举)。三个 action(`execution_detail`/`execution_output_data`/`node_execution_detail`)都先调它拿"已鉴权 execution_id",再查节点;删除不做 team 校验的旧 `_resolve_execution_context`。

决策:D1 不存在/他团队都 404;D2 无主记录的孤儿执行 → 404(deny,安全侧);D3 维持本视图 get_queryset 对 superuser 也按 current_team 过滤;D4 输入缺失 ValidationError(400)、归属 NotFound(404),响应体 `{"detail":...}` 不变。
- 使用组织零查看 → IDOR 只按 `team` 收口,**不并入 usage_team**。

## 测试
- 使用组织:usage 用户 chat(is_test=False)放行 / test(is_test=True)拒;管理用户 chat+test 通;非成员全拒;authorize 三重防护;存量 bot(回填后)行为不变。
- IDOR:跨团队三接口 404;同团队 200;task_result_id 路径越权 404;缺参 400;无 current_team 403。
