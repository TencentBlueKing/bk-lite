# ITSM 技术债审查

2026-11-24，`feature_itsm`，HEAD `8fa8291cb`，含工作区尚未提交的修复。本次结论限于 ITSM 前后端及其调用的公共组件。在线客服和业务对象的未提交功能不作产品验收。分级依据为业务影响，未对出现概率作线上估算。

## 修复与复验（2026-11-24）

T01–T32 的修复已落在本地 `feature_itsm` 工作区。下方清单保留首次扫描时的证据和优先级。

| 项目 | 复验结果 |
|---|---|
| T01–T04、T15–T17 | 已发布版本按引擎定义 ID 启动。真实 Flowable 7.1.0 验证了回启旧版、启动应答丢失后按同一申请键恢复、105 个会签待办跨页同步，以及定时任务中断后继续。 |
| T05–T09、T26、T27、T30、T31 | 验证模板草稿回读、保留布局和规则、跨端条件求值、并行节点字段与附件权限、设计器加载失败保护。Chrome 使用隔离接口数据验证字段显隐、手动取数次数和上传所属任务。 |
| T10–T14、T23–T25 | 业务事务持久化通知。验证 Worker 恢复、接收人失效、回退后再次通知、邮件按邮箱路由和防重。真实本地 HTTP 接收器验证 503 后先核对，再按同一事件标识重投。另用超时异常测试覆盖应答丢失。 |
| T18–T22、T28、T29、T32 | 验证同步和异步导出到期清理、5,000 行 JSON 数据表 Excel 往返与旧格式读取、服务目录查询及访问范围、触发器人员字段生效范围和 SLA 时区回读。Chrome 使用隔离数据验证数据表与投递记录翻页、失败筛选。模块说明已更新。 |

合并后在隔离 PostgreSQL、Flowable、Python 执行器和本地 HTTP 接收器上运行 ITSM 后端测试，681 项通过。以本轮开始时的工作区为基线，ITSM 后端变更的可执行行覆盖 583/630（92.5%，排除测试与迁移）。Web 59 个 ITSM 测试文件共 252 项通过。ITSM ESLint、含测试的 TypeScript 检查和 Web 生产类型检查通过。运行库升级需要应用 `0025_ticket_start_and_schedule_recovery` 和 `0026_delivery_recovery` 并重启 Worker、Beat。

全仓门禁仍有失败。Web 的 3 个 ESLint 错误位于 Monitor 和 RUM。后端全量测试在构建测试库时遇到告警模块的 `NewSessionEventRelation.event` 字段错误，独立运行的演示文稿工具测试有 23 项失败。

分模块提交前，单独检出了排除在线客服和业务对象改动的代码。隔离 PostgreSQL、Flowable 和执行器回归通过 676 项后端测试，前端通过 59 个文件的 252 项测试。此前的 681 项包含留在工作区的两个模块的 5 项测试。

## 首次扫描结论

- 共登记 32 项，高优先级 16 项，中优先级 15 项，低优先级 1 项。优先改待办凭据与目标的绑定、Flowable 定义版本、待办分页核销和表单数据保全。
- 隔离回读证实，已经发布的表单再次保存草稿后，页面会读回旧字段名。字段条件的 OR、数值比较和单叶输入也能在前后端得到不同结果。
- 异步投递要按业务路径验收。触发器动作已有持久化恢复，但普通待办通知、关注通知和外部待办分别走不同路径，各有中断窗口。
- 工单建单存在跨系统提交窗口。报告记录的是代码允许的失败时序，本轮没有证据表明运行库已经发生过错单、漏单或错投消息。
- 数据表 5,000 行数组值导出后不能重新导入，已用实际 Django 视图复现。文件大小及其单元格上限需要纳入导入导出的往返验收。

## 系统结构和扫描范围

门户和工单中心通过 React 页面、表单渲染器和 `useItsmApi` 调用 Django 视图。Django 保存流程版本、节点权限和工单状态，Flowable 持有实际流程实例与待办。详情渲染和操作校验需要在两端选中同一版本、同一个任务。配置编辑、发布与运行分属三条路径，单独验证其中一条覆盖不了保存后回读的问题。

后台由 Celery 调度。站内消息可与业务记录共用数据库事务，IM、外部待办和 MinIO 使用独立服务。审查分别查看了事件何时持久化、谁认领、重复执行如何识别，以及中断后由谁继续处理。分析包含测试、迁移、组织边界、依赖及文档。工作区两个 ITSM 源码目录内的 Python、TS、TSX 共 39,675 行，含测试和迁移。按本地可见 Git 历史统计，近六个月修改最多的是 `useItsmApi.ts`（25 次）、`urls.py`（20 次）、工单视图和工单服务（各 17 次）。代码行数用于选择检查位置，不用于判定缺陷。

## 问题清单

工作量 S 表示局部修改和回归，M 表示跨入口或涉及状态变更，L 表示需要协调多个系统和历史数据。未注明实测的条目依据当前源码调用链和对应异常路径判断。

| ID | 类别 | 代码位置 | 优先级 | 工作量 | 影响及发生条件 | 建议 |
|---|---|---|---|---|---|---|
| T01 | 凭据隔离 | [server/apps/itsm/views/integrations.py:96](server/apps/itsm/views/integrations.py#L96) · [server/apps/itsm/services/todo_sync.py:19](server/apps/itsm/services/todo_sync.py#L19) · [server/apps/itsm/tests/test_integrations.py:156](server/apps/itsm/tests/test_integrations.py#L156) | 高 | S | 待办集成更换接收地址时，留空仍保留原令牌。下一次投递会向新地址发送旧凭据。已有测试覆盖同主机换路径，没有覆盖换主机。 | 将凭据绑定到获准的接收目标。切换目标清除旧凭据并提示重新授权，用两个虚拟目标做回归。 |
| T02 | 流程版本 | [server/apps/itsm/views/api.py:404](server/apps/itsm/views/api.py#L404) · [server/apps/itsm/views/m2.py:443](server/apps/itsm/views/m2.py#L443) · [server/apps/itsm/flowable/client.py:47](server/apps/itsm/flowable/client.py#L47) · [server/apps/itsm/services/ticket/service.py:479](server/apps/itsm/services/ticket/service.py#L479) | 高 | M | 启用旧版本只切换 Django 的当前版本。建单和重新打开只向 Flowable 传流程 key，丢失选中的定义版本。不同组织也允许同 key，共享引擎时还有选错定义的风险。 | 发布时记录准确的定义 ID，启动时用 ID。对旧部署按 deployment_id 核对回填。 |
| T03 | 待办同步 | [server/apps/itsm/flowable/client.py:53](server/apps/itsm/flowable/client.py#L53) · [server/apps/itsm/services/ticket/service.py:200](server/apps/itsm/services/ticket/service.py#L200) | 高 | M | 任务和子实例各只取第一页，随后把未出现的本地任务标为完成。分页组件复核中，接口声明共 3 项，客户端只返回第 1 项。 | 完整读取所有页及支持的子流程层级。任一页失败时中止核销，测试超过单页的会签。 |
| T04 | 建单一致性 | [server/apps/itsm/services/ticket/service.py:40](server/apps/itsm/services/ticket/service.py#L40) · [server/apps/itsm/services/ticket/service.py:77](server/apps/itsm/services/ticket/service.py#L77) | 高 | L | 普通提单在本地事务内启动远程流程，之后仍会同步待办、落本地数据。远端已启动而后续失败时，本地事务回滚，重新提交可能启动第二个实例。 | 先持久化申请和稳定业务键，区分未启动、结果未知和已绑定；按业务键核对未知结果。 |
| T05 | 表单数据保全 | [web/src/app/itsm/form/designer/[id]/page.tsx:45](web/src/app/itsm/form/designer/%5Bid%5D/page.tsx#L45) · [server/apps/itsm/views/api.py:123](server/apps/itsm/views/api.py#L123) · [server/apps/itsm/services/form/schema.py:81](server/apps/itsm/services/form/schema.py#L81) · [server/apps/itsm/services/form/validator.py:79](server/apps/itsm/services/form/validator.py#L79) | 高 | S | 模板编辑页只用 version、fields 重建 schema。保存含顶层 rules、layout 的模板会丢掉这些配置，计算和条件必填随之变化。 | 从已加载 schema 派生修改，只替换 fields。覆盖含布局和计算规则的保存、发布、提单。 |
| T06 | 草稿版本 | [server/apps/itsm/views/api.py:84](server/apps/itsm/views/api.py#L84) · [server/apps/itsm/views/api.py:110](server/apps/itsm/views/api.py#L110) · [server/apps/itsm/views/api.py:127](server/apps/itsm/views/api.py#L127) · [web/src/app/itsm/form/designer/[id]/page.tsx:52](web/src/app/itsm/form/designer/%5Bid%5D/page.tsx#L52) | 高 | S | 发布新版本后仍保留较低编号草稿。保存修改写入旧草稿，编辑页按最高版本重新读取。隔离视图实测写入字段名 B，读回 A。 | 明确编辑态取草稿、运行态取发布版。加入发布后继续编辑并重新打开的用例。 |
| T07 | 表单条件 | [web/src/app/itsm/components/condition-builder.tsx:6](web/src/app/itsm/components/condition-builder.tsx#L6) · [web/src/app/itsm/components/form-renderer.tsx:78](web/src/app/itsm/components/form-renderer.tsx#L78) · [server/apps/itsm/services/form/rules.py:10](server/apps/itsm/services/form/rules.py#L10) | 高 | M | 渲染器把 OR 当成 AND，未识别的比较直接返回真，单叶条件可抛 TypeError。三组相同输入在前后端给出不同结果，可能隐藏必须填写的字段。 | 用相同的规则结构和语义处理单叶、条件组及各操作符；跨端共用一套输入输出样例。 |
| T08 | 节点权限契约 | [web/src/app/itsm/components/ticket-actions.tsx:89](web/src/app/itsm/components/ticket-actions.tsx#L89) · [web/src/app/itsm/components/ticket-detail-page.tsx:147](web/src/app/itsm/components/ticket-detail-page.tsx#L147) · [server/apps/itsm/views/field_fetch.py:108](server/apps/itsm/views/field_fetch.py#L108) · [server/apps/itsm/services/ticket/service.py:387](server/apps/itsm/services/ticket/service.py#L387) | 高 | M | 同一人可处理两个并行任务时，操作按钮可选择第二个任务，表单和动态取数仍按第一个任务过滤。第二个节点独有的必填字段可能无法填写。 | 把选中的 task_id 用于详情、取数和提交，逐次复核该任务权限。 |
| T09 | 设计器写入 | [web/src/app/itsm/form/designer/[id]/page.tsx:42](web/src/app/itsm/form/designer/%5Bid%5D/page.tsx#L42) · [web/src/app/itsm/form/designer/[id]/page.tsx:86](web/src/app/itsm/form/designer/%5Bid%5D/page.tsx#L86) · [web/src/app/itsm/workflow/designer/[id]/page.tsx:93](web/src/app/itsm/workflow/designer/%5Bid%5D/page.tsx#L93) · [server/apps/itsm/views/api.py:345](server/apps/itsm/views/api.py#L345) | 高 | M | 加载未完成或失败时编辑器保留初始表单或流程，保存按钮仍可操作，有覆盖现有草稿的窗口。 | 仅在当前资源加载成功后允许写入。用慢响应、加载失败和切换资源验证。 |
| T10 | 外部待办恢复 | [server/apps/itsm/services/todo_sync.py:84](server/apps/itsm/services/todo_sync.py#L84) · [server/apps/itsm/services/todo_sync.py:95](server/apps/itsm/services/todo_sync.py#L95) · [server/apps/itsm/views/integrations.py:136](server/apps/itsm/views/integrations.py#L136) | 高 | M | 投递先标 running 再发 HTTP。进程在写终态之前退出，定时任务只扫 pending，手动重试只收 failed，这条待办会卡住。 | 增加领取时间和过期核对；沿用原事件键，对不能确认幂等的接收方留人工核对状态。 |
| T11 | 通知可靠性 | [server/apps/itsm/services/ticket/service.py:199](server/apps/itsm/services/ticket/service.py#L199) · [server/apps/itsm/signals.py:57](server/apps/itsm/signals.py#L57) | 高 | M | 普通节点待办、关注人评论提醒在数据库提交后由进程内回调发出。提交后回调前退出，业务记录存在，却没有待投递记录供 Worker 恢复。 | 同事务落通知事件，Worker 按稳定事件键认领。让测试刻意丢弃提交回调再恢复。 |
| T12 | 通知有效身份 | [server/apps/itsm/services/trigger_notice.py:105](server/apps/itsm/services/trigger_notice.py#L105) · [server/apps/itsm/services/trigger_notice.py:173](server/apps/itsm/services/trigger_notice.py#L173) · [server/apps/itsm/services/sla_notices.py:16](server/apps/itsm/services/sla_notices.py#L16) | 高 | S | 触发器用 disabled 判断账号可用，漏查账号到期时间。仍有有效 IM 映射的过期账号可能收到工单通知。SLA 接收人查询已考虑到期时间。 | 复用统一的有效账号条件，恢复发送时也校验原快照内的账号。 |
| T13 | 邮件路由 | [server/apps/itsm/tasks.py:32](server/apps/itsm/tasks.py#L32) · [server/apps/itsm/tasks.py:40](server/apps/itsm/tasks.py#L40) · [server/apps/itsm/models/extend.py:298](server/apps/itsm/models/extend.py#L298) | 高 | M | 启用本地邮件收取后，取全库第一条有效规则，不按邮箱和组织选流程。建单固定为测试单且未写入 service。多个邮箱并存时可能错投。 | 先根据接收邮箱确定组织与规则，校验服务归属，区分正式收件与显式演练。 |
| T14 | 邮件建单防重 | [server/apps/itsm/tasks.py:54](server/apps/itsm/tasks.py#L54) · [server/apps/itsm/tasks.py:57](server/apps/itsm/tasks.py#L57) | 高 | M | 邮件建单成功后才重命名文件。进程中断、移动失败或两次轮询重叠都可能重复建单，单封异常也会中断本轮扫描。 | 持久化收件唯一标识、领取状态和工单关联。按邮箱及消息标识去重，逐封隔离失败。 |
| T15 | 写接口契约 | [server/apps/itsm/views/api.py:361](server/apps/itsm/views/api.py#L361) · [server/apps/itsm/views/api.py:397](server/apps/itsm/views/api.py#L397) · [server/apps/itsm/views/ticket_operations.py:89](server/apps/itsm/views/ticket_operations.py#L89) | 高 | S | 流程发布和手工建子单入口缺少 POST 限制。有权限的读取类请求可能执行写操作；发布已发布版本还可再次部署。 | 限定 HTTP 方法，锁定待发布草稿并识别重复请求，验证 GET、HEAD 无业务副作用。 |
| T16 | 测试工单隔离 | [server/apps/itsm/views/ticket_operations.py:95](server/apps/itsm/views/ticket_operations.py#L95) · [server/apps/itsm/services/ticket/subforms.py:38](server/apps/itsm/services/ticket/subforms.py#L38) · [server/apps/itsm/services/ticket/service.py:64](server/apps/itsm/services/ticket/service.py#L64) | 高 | S | 手工子单未继承父单测试标记。当测试来自父单而非流程配置时，子单可能成为普通工单并投递外部消息。手工入口还缺少动态取数校验需要的当前用户身份。 | 继承父单测试标记，并以当前请求初始化工单服务。用带动态字段的测试父单验证。 |
| T17 | 计划执行恢复 | [server/apps/itsm/services/schedules.py:84](server/apps/itsm/services/schedules.py#L84) · [server/apps/itsm/services/schedules.py:96](server/apps/itsm/services/schedules.py#L96) · [server/apps/itsm/services/schedules.py:162](server/apps/itsm/services/schedules.py#L162) | 中 | M | 调度领取事务先推进计划时间，事务结束后才执行。中途退出会留下 running，已领取的单次计划没有再次进入扫描的入口。 | 按执行阶段恢复。已有工单则核对关联，远端结果未知时禁止盲目重建。 |
| T18 | 导出保留期 | [server/apps/itsm/services/ticket/export_jobs.py:107](server/apps/itsm/services/ticket/export_jobs.py#L107) · [server/apps/itsm/services/ticket/export_jobs.py:115](server/apps/itsm/services/ticket/export_jobs.py#L115) · [server/apps/itsm/views/ticket_export.py:38](server/apps/itsm/views/ticket_export.py#L38) | 中 | M | 七天后异步导出正文靠原用户再访问或提交时清理。同步导出也保存完整正文，却不在该清理范围。人员离开后数据可能长期占库。 | 按全局到期时间分批清正文，保留必要审计元数据，并覆盖旧同步任务。 |
| T19 | Excel 往返 | [server/apps/itsm/services/import_copy.py:144](server/apps/itsm/services/import_copy.py#L144) · [server/apps/itsm/services/import_copy.py:150](server/apps/itsm/services/import_copy.py#L150) · [server/apps/itsm/services/import_copy.py:193](server/apps/itsm/services/import_copy.py#L193) | 中 | M | 把所有需 JSON 还原的单元格坐标写进一个 Excel 单元格，超过 32,767 字符后被截断。用 5,000 行数组字段经实际导出和导入视图验证，导出成功，原文件导入返回 400。 | 将坐标分行写入隐藏工作表，给格式版本号。测试新旧文件、空值和大表。 |
| T20 | 数据表查询 | [server/apps/itsm/views/m2.py:701](server/apps/itsm/views/m2.py#L701) · [server/apps/itsm/views/m2.py:733](server/apps/itsm/views/m2.py#L733) · [server/apps/itsm/views/m2.py:738](server/apps/itsm/views/m2.py#L738) | 中 | M | 读表结构和表数据也在事务中锁表的主记录，行列表一次加载全部 JSON。同一数据表的读写互相等待，大表第一页也传输全表。 | GET 使用普通查询和服务端分页。保留结构与行写入之间的一致性锁。 |
| T21 | 服务权限查询 | [server/apps/itsm/services/service_access.py:12](server/apps/itsm/services/service_access.py#L12) · [server/apps/itsm/services/service_access.py:24](server/apps/itsm/services/service_access.py#L24) · [server/apps/itsm/views/field_fetch.py:97](server/apps/itsm/views/field_fetch.py#L97) | 中 | M | 普通用户按一个 ID 查服务或做字段取数时，先加载全组织处理组和已发布服务，在 Python 算出全部允许的 ID 才筛目标。 | 先限定目标服务或流程，再查相关组。目录列表单独走分页搜索并复用可见性判定。 |
| T22 | 触发器配置查询 | [server/apps/itsm/services/trigger_notice.py:133](server/apps/itsm/services/trigger_notice.py#L133) · [server/apps/itsm/services/trigger_fields.py:109](server/apps/itsm/services/trigger_fields.py#L109) | 中 | M | 保存通知动作时，为校验表单人员字段读取全组织服务、表单与流程结构，再过滤生效范围。多动作会重复这段工作。 | 把范围和所需字段传入查询，在一次保存内复用结果。 |
| T23 | 请求时延 | [server/apps/itsm/services/trigger_delivery.py:19](server/apps/itsm/services/trigger_delivery.py#L19) · [server/apps/itsm/services/trigger_delivery.py:124](server/apps/itsm/services/trigger_delivery.py#L124) · [server/apps/itsm/services/knowledge_attachments.py:25](server/apps/itsm/services/knowledge_attachments.py#L25) · [server/apps/itsm/services/knowledge_attachments.py:34](server/apps/itsm/services/knowledge_attachments.py#L34) | 中 | M | on_commit 在提交后的请求线程中执行。工单触发通知仍可能等待 IM，知识文章删除可逐件等待对象存储。 | 提交后只投递任务，保留现有定时兜底。以慢通道验证接口完成时间和最终投递结果。 |
| T24 | 通知事件去重 | [server/apps/itsm/services/external_jobs.py:86](server/apps/itsm/services/external_jobs.py#L86) · [server/apps/itsm/services/external_jobs.py:203](server/apps/itsm/services/external_jobs.py#L203) | 中 | S | 通知节点站内事件键按单、节点和流程实例生成，回退后再次到达同节点会合并为第一次的消息。 | 事件键纳入一次有效到达的 job_id，同时保留同一作业重领防重。 |
| T25 | 知识发布一致性 | [server/apps/itsm/services/external_jobs.py:115](server/apps/itsm/services/external_jobs.py#L115) · [server/apps/itsm/views/knowledge.py:103](server/apps/itsm/views/knowledge.py#L103) | 中 | S | 知识节点允许直接发布空正文文章，也没有建立与来源工单的关联。知识库管理页有正文发布校验。 | 复用发布校验，保存来源工单。正文为空时记录节点失败或按既定策略存草稿。 |
| T26 | 附件权限契约 | [web/src/app/itsm/components/form-renderer.tsx:45](web/src/app/itsm/components/form-renderer.tsx#L45) · [server/apps/itsm/views/attachments.py:17](server/apps/itsm/views/attachments.py#L17) | 中 | S | 已有工单的表单上传附件时未传 ticket_id。只有查看和处理权限的处理人会被当成提单用户要求 ticket-Add。 | 传入当前工单标识，在后端校验该单及节点。覆盖具备处理权限、无新建权限的用户。 |
| T27 | 字段联动 | [web/src/app/itsm/components/field-fetch-control.tsx:38](web/src/app/itsm/components/field-fetch-control.tsx#L38) · [web/src/app/itsm/components/field-fetch-control.tsx:58](web/src/app/itsm/components/field-fetch-control.tsx#L58) | 中 | S | 手动刷新只在第一次点击前阻止自动取数。点击一次后，变更依赖字段就会再次调用 API 或 Python。 | 每次手动点击记录当次输入，只对该快照发起请求，依赖变化时标成待刷新。 |
| T28 | 投递可观测性 | [server/apps/itsm/views/integrations.py:105](server/apps/itsm/views/integrations.py#L105) · [web/src/app/itsm/form/integrations/workspace.tsx:179](web/src/app/itsm/form/integrations/workspace.tsx#L179) | 中 | M | 集成详情只返回最近 20 次执行、30 条投递。旧失败记录掉出窗口后，管理员无法从列表找到并重试。 | 为历史提供按状态和游标的服务端分页，优先显示未处理失败。 |
| T29 | 日历配置契约 | [server/apps/itsm/views/m2.py:584](server/apps/itsm/views/m2.py#L584) · [server/apps/itsm/views/m2.py:598](server/apps/itsm/views/m2.py#L598) · [web/src/app/itsm/rule/calendars/page.tsx:54](web/src/app/itsm/rule/calendars/page.tsx#L54) | 中 | S | 配置支持保存时区，读取服务窗口却省略时区。管理员看到相同的工作时间，无法判断 SLA 使用哪一时区。 | 返回和展示实际时区，验证非默认时区保存后重新打开。 |
| T30 | 错误恢复 | [web/src/app/itsm/components/ticket-detail-page.tsx:64](web/src/app/itsm/components/ticket-detail-page.tsx#L64) · [web/src/app/itsm/components/ticket-detail-page.tsx:113](web/src/app/itsm/components/ticket-detail-page.tsx#L113) | 中 | S | 打开无效或失去权限的工单时，加载失败只弹一次提示，页面主体仍显示加载中。 | 区分加载、无权或不存在、暂时失败三种结果，提供返回列表或重试。 |
| T31 | 测试契约 | [web/src/app/itsm/rule/triggers/trigger-editor.test.tsx:67](web/src/app/itsm/rule/triggers/trigger-editor.test.tsx#L67) · [web/src/app/itsm/components/resource-board.test.tsx:18](web/src/app/itsm/components/resource-board.test.tsx#L18) · [web/tsconfig.build.json:13](web/tsconfig.build.json#L13) | 中 | S | 含测试的 TypeScript 检查在 ITSM 测试文件报 19 处类型错误。构建配置排除了测试文件，Vitest 通过也无法发现这些契约差异。 | 按 Testing Library 实际签名修正测试查询，单列测试文件的类型检查。 |
| T32 | 文档漂移 | [server/apps/itsm/README.md:3](server/apps/itsm/README.md#L3) · [server/apps/itsm/README.md:13](server/apps/itsm/README.md#L13) | 低 | S | 模块自述开头仍写模型和业务接口留到后续，同一文档却已记录上线功能与运行依赖。 | 改成当前入口、运行依赖、调度与恢复说明，把早期里程碑放回历史章节。 |

## 建议的前五批修复

1. **先修凭据绑定（T01）。** 待办和外部 API 共用目标变更判定，接收方变化时使旧令牌失效。用模拟接收器验证同目标保留、换接收方清除、重新授权成功三个场景。
2. **按准确版本启动流程（T02）。** 发布时按部署查回定义 ID，回填已有版本后让建单和重新打开都使用定义 ID。用两个不同审批节点的版本发布、切回 V1、提单、重新打开，核对引擎的实际节点。再覆盖两个组织同 key 的情况。
3. **分页读取全部待办后再核销（T03）。** 遍历任务和子实例页面，全部成功再与本地待办对比。覆盖第二页仍有活动任务、读取第二页失败、嵌套子实例三种情况。
4. **修表单的保存和回读（T05、T06、T09）。** 先把草稿与当前发布版的选择写成行为测试，再修编辑器序列化和加载状态。验收从带条件规则的模板开始，发布后修改一个字段、保存并重新打开，检查字段名和原规则。
5. **为建单持久化启动意图（T04）。** 建单请求、业务键和引擎实例建立可查询的对应关系。分别在引擎调用前、引擎已成功但本地未记录、同步待办失败处中断，核对同一申请最终只关联一个实例。

## 首次扫描建议的小改动

- [x] T15、T16，限制写操作方法并让手工子单继承父单的测试状态和操作人身份。
- [x] T12，统一通知接收人的账号到期检查。
- [x] T26，已有关联工单的附件上传传递工单标识，用仅有处理权限的账号验证。
- [x] T29、T30，显示 SLA 窗口时区，并让无权或失效的工单有明确的结束状态。

## 已核对且建议保留的现有设计

- 触发器 IM 发送前记录逐渠道、逐收件人占位。外部发送结果未知时保留待核对语义，避免重复发送。在规划普通通知恢复时应沿用这一约束。[server/apps/itsm/services/trigger_delivery.py:109](server/apps/itsm/services/trigger_delivery.py#L109)
- 知识库上传与清理使用同一条记录加锁，防止慢上传尚未结束就被清理。T23 的调整点是删除触发后的等待方式。[server/apps/itsm/views/knowledge.py:214](server/apps/itsm/views/knowledge.py#L214) · [server/apps/itsm/services/knowledge_attachments.py:30](server/apps/itsm/services/knowledge_attachments.py#L30)
- 子表只回传可见单元格并给行附签名，使服务端能把合法修改合回原行。已有测试覆盖隐藏列保留，T08 的修复应继续按选定任务过滤字段。[server/apps/itsm/services/form/table_columns.py:27](server/apps/itsm/services/form/table_columns.py#L27) · [server/apps/itsm/tests/test_review_regressions.py:420](server/apps/itsm/tests/test_review_regressions.py#L420)
- 定时建单已按计划时点防重，SLA 已在工单和计时记录加锁后判断是否投递。T17 需要处理已领取但未完成的执行，不能靠直接重跑解决。[server/apps/itsm/services/schedules.py:90](server/apps/itsm/services/schedules.py#L90) · [server/apps/itsm/services/sla_notices.py:76](server/apps/itsm/services/sla_notices.py#L76)

## 验证与限制

| 验证 | 本轮结果 |
|---|---|
| 后端 ITSM 测试 | 隔离 SQLite，启用 ITSM、Celery 及临时签名配置后 624 通过、8 跳过，包含工作区现有测试。按 coverage JSON 剔除 tests、migrations，测得业务源文件行覆盖率约 86.5%（7,660 / 8,856）。本轮未对 PostgreSQL 和真实 Flowable 重新做故障注入。 |
| Web ITSM 测试 | 首轮并发跑 227 通过、1 条触发器编辑器用例达到默认 5 秒超时。限制为 2 个 worker 后，全量 56 个文件、228 条通过。 |
| 静态检查 | ITSM ESLint 通过；用项目生产配置 `tsc -p tsconfig.build.json --noEmit` 通过。额外含测试的默认 TypeScript 检查失败，其中 19 条诊断在 ITSM 测试文件，见 T31。 |
| 定向复核 | 真实表单视图在隔离 SQLite 上复现 T06；对同一输入执行实际前端条件函数与 Python 实现复现 T07；实际 Flowable 客户端结合分页响应桩复核 T03；隔离 SQLite 中经真实数据表视图复现 T19。 |
| 依赖漏洞工具 | pnpm 配置的镜像未提供安全公告接口，本机 pip-audit 因 Python 的 Expat 动态库不匹配而无法启动。依赖漏洞清单未验证。没有安装全局工具，也未将项目依赖清单改发其他 registry。 |
| 工具覆盖 | 本机未发现本项目可直接调用的 knip、madge、depcheck、ruff、vulture、pydeps、mypy。未据此判断无死代码、无循环依赖或严格类型检查通过。 |

## 首次扫描提出的运营问题

- 邮件目录轮询是否计划作为多组织正式入口？若仅用于演示，T13、T14 可先通过限制启用范围和标明演练模式处理。若正式收件，则应在扩大使用前修复。
- 保存旧同步导出正文是否有独立保留期要求？这会影响 T18 的清理时限及是否保留文件审计摘要。
- 实际待办接收方是否都按事件键提供幂等保证？这决定 T10 中哪些未知结果能自动恢复，哪些需要人工核对。
