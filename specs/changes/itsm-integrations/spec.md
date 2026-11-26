# ITSM 集成

用户已确认移除数据源，保留数据表，在表单与数据新增集成，复用平台网关和隔离执行器。

## 实施计划
1. 移除数据源菜单和 CRUD 入口（保留历史表，避免破坏已有数据）；新增集成模型与租户/操作权限测试。
2. API 集成复用 OpenAPI 注册目录、schema、dispatcher 和实时用户授权；保存 endpoint 与参数，不复制 API 定义。
3. Python 集成复用 TransformExecutor，上传 UTF-8 .py（100KB），协议 transform(rows, params)，隔离服务缺失时明确失败，不降级本机执行。
4. 待办对接复用现有推送入口，按域配置，带事件和幂等键；记录投递状态，支持测试和失败重试。
5. 自动节点选择集成及输入参数；输入支持 ${form.key}、${ticket.sn} 等完整值引用。执行失败不推进流程。
6. 统一列表/配置/调试页面，本地验证权限、API schema、脚本失败/成功、待办生命周期和流程节点。

## 权限与审计
- 列表 data-View；保存/调试 data-Edit（新增 data-Add，删除 data-Delete）。流程读配置另允许 workflow-View，但不返回脚本和参数。
- API 调试使用当前用户身份；流程执行使用该流程版本设计维护人的实时权限（手动触发用当前操作者），不借用集成维护人权限，停用账号/权限收回后拒绝。不使用 system 超管。
- 每次执行记录状态、耗时、操作者和错误码；请求参数/输出仅回显给调试者，不落执行审计记录。
- 待办 HTTP 使用已有 safe_request 防 SSRF，不允许跳转；以事件 ID 供接收方幂等，失败不自动盲目重复 API/脚本。

## 本地验收（2026-11-13）
- 已移除数据源页面、菜单及 CRUD/测试接口；保留历史数据库表，不删除用户数据。
- 浏览器创建平台 `GET itsm/tickets` 集成，复用参数文档并成功调试。
- 浏览器上传 `.py` 文件并执行，输入 amount=100 / rate=2，输出 result=200；调试与流程记录均可查看。
- 真实隔离 Runner 验证成功、非法 import 拒绝、死循环约 5 秒终止。
- 本地 HTTP 接收器在测试数据库运行 create/update/close；503 失败重试使用相同 event_id，成功后不重复投递。没有改动生产白名单。
- 真实 Flowable 工作流 start → submit → API → Python → end 完成，结果显式写回 integration_result 字段。默认审计不保存 API/脚本输出。
- ITSM 完整回归 175 项通过；随后增加 API Token 范围与流程执行身份回归，集成定向测试 19 项通过。新增后端模块覆盖率约 91%。
- 前端 8 项测试、改动文件 eslint、完整 type-check 和 diff whitespace 检查通过。
- 全仓 pnpm lint 存在 3 个未修改文件中的既有错误（monitor automaticPolicyApply、rum-bootstrap、rumBootstrap）。make test 的应用测试在收集阶段等待 195 秒后中断；内嵌 PPT 工具套件 23 失败 / 719 通过，未改动这些模块。

## 使用及边界
- API 选择器接入平台已注册、带 schema 的内部 API。外部网关服务只有文档链接而没有端点 schema，继续在平台 API 文档维护，不在 ITSM 复制网关配置。
- Python 遵循平台已有 transform(rows, params) → list[dict] 协议，复用 agents/ops-analysis-transform-runner。设置 TRANSFORM_RUNNER_URL / TRANSFORM_RUNNER_TOKEN；本地已启动 8099 服务，不向仓库写入令牌。
- 待办对接为 ITSM 向外部系统推送，接收方按 task_id upsert，按 event_id 幂等；不开放绕过工单权限的外部审批回调。尚未配置具体客户的外部待办系统。
- 集成停用后不继续执行；投递状态 running 表示结果可能未确认，不自动盲目重放。
