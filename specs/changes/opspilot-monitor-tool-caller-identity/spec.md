# OpsPilot Monitor 工具改用调用方身份

Status: ready

## Problem Statement

OpsPilot Skill 内置 Monitor 工具当前要求在 Skill 配置中填写登录账号、密码，并可手选组织 ID。运维人员不愿把个人凭据写进 Skill；手填组织也容易与真实「当前组」不一致，存在越权或配错范围的风险。希望工具直接沿用调用方已登录身份与当前组数据，而不是再要一套账号密码。

## Solution

在交互式 HTTP 入口与 Skill 直接执行场景下，网关受理请求时把已校验的用户身份、当前组，以及（若有）是否包含子组写入工作流/Agent 运行时上下文。Monitor 工具只从该上下文组装 Monitor RPC 所需的 `user_info`，不再二次密码登录，也不再暴露可被模型改写的身份参数。Skill 配置 UI 去掉账号、密码与组织选择，仅说明「使用调用方登录身份与当前组」。定时任务、IM 渠道等无登录态入口若挂载了 Monitor 工具，返回明确错误。

## User Stories

1. As a 已登录的运维人员, I want 在 Web/Mobile/嵌入式等会话里使用挂了 Monitor 的 Skill 或工作流时自动按我的身份与当前组查监控, so that 我不必在 Skill 里保存账号密码。
2. As a Skill 配置者, I want Monitor 工具无需填写账号、密码和组织, so that 配置更简单且不沉淀凭据。
3. As an OpenAPI 调用方, I want 使用 API Secret 调用时按密钥解析出的用户与绑定组访问 Monitor, so that 程序化调用与密钥授权范围一致。
4. As a 平台使用者, I want 模型不能改写 Monitor 所用的用户或组织, so that 监控数据范围始终等于受理时的合法当前组。
5. As a Bot 运维人员, I want 定时或企微/钉钉等无登录态触发若调用了 Monitor 时得到明确失败提示, so that 我知道该入口尚不支持监控工具而不是拿到空结果或静默跳过。

## Implementation Decisions

- 第一版覆盖范围仅限交互式 HTTP 入口（含 Web Chat、Mobile、Embedded、AGUI、OpenAI 兼容、Restful、Studio 试跑）以及 Skill 详情页直接执行；Celery、企微、钉钉、公众号、NATS 等不纳入身份注入。
- 身份材料为入口已校验结果，不下传原始 Bearer/JWT/API Secret。快照字段至少包括用户名、域、当前组 ID，以及是否包含子组。
- 「当前组」来源：常规登录以请求当前组（如 `current_team`）为准，并校验该用户属于该组；缺组或校验失败则拒绝受理，不入队、不回落到 Skill/Bot 归属组。OpenAPI 以 `UserAPISecret` 实例（含未显式 mark）解析出的绑定组为准，不再另取 cookie 当前组；JWT/会话身份不得复用 `UserAPISecret` 作为 DTO。
- `include_children`：常规登录若能读到对应 cookie 则写入快照；读不到或非常规登录（含 API Secret）默认不包含子组。
- 身份必须在 HTTP 受理成功时写入 `flow_input` / Agent 运行时 `extra_config`（或等价可传递上下文），随异步 worker 执行；工具执行阶段不得再依赖原始 HTTP 请求。
- 删除 Monitor 内置工具构造参数中的账号、密码、域、组织 ID；已保存的旧 kwargs 忽略（可打日志），不作为运行时凭据。
- 身份只进入运行时 configurable，不得进入工具 schema、不得进入 `extra_param_prompt`；子工具仅保留业务查询参数。模型传入的身份类字段一律忽略或拒绝。
- Monitor 调用 Monitor RPC 时仍使用既有 `user_info` 形状（用户、域、组、是否含子组），但由运行时身份组装，不再 `check_password` 二次登录。
- 须保证 `langchain:monitor` 可被工具加载器正确注册与加载；builtin 负 ID 工具的运行时参数须能进入 configurable，而不是只进 prompt 描述。
- Skill 工具选择 UI：去掉 Monitor 的凭据与组织选择器，仅展示「使用调用方登录身份与当前组」说明；保存时不再写入旧凭据字段。
- 非覆盖范围内的触发类型若执行到 Monitor：返回明确、可理解的中文错误，尽量点名触发来源（Celery / NATS / 企微 / 钉钉等），说明缺少调用方身份快照；禁止静默空结果、禁止回退已删除的密码配置。Celery 周期任务须在 `flow_input` 写入 `entry_type=celery`，便于 Agent 映射 `trigger_type=unattended` 与报错归因。

## Testing Decisions

- 好测试只断言外部行为：给定入口身份与组，工具组装出的 Monitor `user_info` 是否正确；缺身份/缺组/非成员/非 A 入口是否失败；模型侧参数无法覆盖身份。
- 优先接缝：Monitor 运行时身份解析（由 configurable 组装 `user_info`，替代原密码鉴权）；交互式入口受理时的身份快照（含 JWT 当前组与 API Secret 绑定组、`include_children` 缺省）；非 A 触发调用 Monitor 的错误路径（含按 entry/trigger 点名的文案，以及 Agent 不合成身份）；builtin 工具描述不再要求凭据参数。
- 既有 `test_monitor_tools` 中基于 username/password 的鉴权用例应改为运行时身份场景，并保留失败路径覆盖。
- 入口快照与 Agent/chat 透传优先用现有 workflow / chat flow / OpenAPI token 校验测试风格做聚焦单测或轻量集成，不要求首期全渠道 E2E。

## Out of Scope

- Celery 定时、企微/钉钉/公众号、NATS 等无登录态入口的服务账号或独立凭据方案。
- 修改 Monitor RPC 协议本身，或监控产品侧的权限模型。
- 为 Monitor 重新引入 Skill 级可配置组织覆盖或双模密码回退。
- 向量、知识库、其它内置工具的身份改造（除非为共享注入上下文所必需的最小接线）。
- Playwright/Cypress 全链路浏览器 E2E（本仓当前无该门禁要求）。

## Further Notes

- 与既有 CMDB 类工具「用 `user_id` + team，不靠密码」的方向一致，但本变更明确以受理时快照为准，并禁止 LLM 改写。
- 当前工作流侧普遍只松散传递 `user_id`，Agent 侧的 `group` 并未稳定进入工具 configurable；实现时需一并打通透传，否则仅改 Monitor 工具仍会缺组。
- 对齐会话结论见 grill-me：范围 A、已校验身份、请求当前组 + 成员校验、删除凭据、受理快照、API Secret 用绑定组、身份对 LLM 不可见、UI 去配置、`include_children` cookie 或缺省 false、非 A 明确报错。
