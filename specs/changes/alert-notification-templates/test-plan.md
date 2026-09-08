# 自定义通知模板测试与验收计划

状态：测试设计，未新增或运行本功能的可执行测试。

关联方案：[spec.md](./spec.md)。仅用户明确要求实施后编写测试代码。

## 1. 测试目标和接缝

本计划包含“相关回归测试”和“相关性规则到最终通知的完整关联链路测试”。
不能只凭 CRUD 成功、编辑器显示 HTML 或发送函数被 mock 调用就判定功能完成。

| 接缝 | 可观察输入/输出 | 建议测试位置（实施时新增） |
|---|---|---|
| 纯渲染 Interface | 模板 + 普通上下文 → 标题/正文/诊断 | `server/apps/alerts/tests/test_notification_template_render_pure.py` |
| 模板配置 Interface | HTTP 请求 → 授权响应、版本冲突、引用保护 | `server/apps/alerts/tests/test_notification_template_views.py` |
| 绑定配置 Interface | 策略/全局配置请求 → 合法绑定或字段错误 | `server/apps/alerts/tests/test_notification_template_binding_service.py` |
| 通知生成与投递 Interface | 生命周期动作 → 持久意图 → 发送内容/结果 | `server/apps/alerts/tests/test_notification_template_delivery_service.py` |
| 告警完整关联链路 | 事件、规则、分派策略 → 真实告警和通知参数 | `server/apps/alerts/tests/test_notification_template_pipeline.py` |
| Web 用户交互 | 编辑/选择/预览/保存 → 展示与提交 payload | alarm-local Vitest 测试与 Storybook |
| 已确认测试渠道 | 实际邮件/机器人消息 → 平台实际效果 | 人工验收记录；自动化默认不外发 |

仅替换外部边界：SMTP/HTTP/NATS provider、目录查询、不可用的外部存储/时钟。
不能 mock 本次要验证的模板选择、渲染、继承或 Outbox 状态机。
期望文本独立写出，不用同一个渲染函数计算 expected。

## 2. 纯渲染和格式测试

| ID | 场景 | 必须断言 |
|---|---|---|
| R01 | 中文 HTML 模板与真实字段 | 表格/内联样式保留；标题正文替换正确；不自动追加接收人 |
| R02 | 企微 Markdown 模板 | 手写标题、加粗、引用、换行原样符合支持的语法 |
| R03 | 一个模板同时配邮件和企微 | 同一告警分别得到 HTML 和 Markdown，不复用同一正文 |
| R04 | 标题与正文含未知固定变量 | 保存/预览字段错误；不能发送残留占位符 |
| R05 | 合法可选富化路径不存在 | 显示 `—`，返回 missing-fields；不阻断通知 |
| R06 | 字段值为 0/false/空字符串 | 0 和 false 保留；空值按既定默认显示 |
| R07 | 变量值包含另一段 `{{...}}` | 不二次求值，不泄露其他字段 |
| R08 | 富化当前对象/历史数组/冲突主值 | 使用既有解析规则；主值稳定；不输出 `_meta` |
| R09 | `__class__`、私有路径、调用、过滤器、循环 | 均被拒绝，不产生执行副作用 |
| R10 | HTML 中告警内容是 `<script>` 或闭合标签 | 以文本显示，不改变用户 HTML 结构、不执行 |
| R11 | HTML 原文含脚本、事件、危险 URL、CSS url/expression | 明确拒绝；错误不泄露敏感模板内容 |
| R12 | 标签名/属性/CSS/URL/注释位置插入变量 | 校验拒绝，不依赖简单字符串替换 |
| R13 | Markdown 变量含标签、@all、反引号等 | 作为普通数据，不注入平台指令或伪造排版 |
| R14 | 标题含 CR/LF 或超过标题限制 | 拒绝或按已锁定契约规范化，不能注入邮件头 |
| R15 | 模板/输出中文 UTF-8 字节超限 | 按字节计数，保存拒绝；运行时有界回退，不截坏结构 |
| R16 | 200 次变量边界、深路径、大列表、巨大源字段 | 展开前限制资源，无无界 stringify/复制 |
| R17 | 汇总 0/1/10/11 条告警 | 总数/展示数/省略数准确；固定排序；最多展示 10 条 |
| R18 | 汇总变量出现在单告警模板，或反向使用 | 明确拒绝，不隐式取 alerts[0] |
| R19 | 负责人和本次接收人不同 | 两个变量分别准确，不将提醒名单显示成负责人 |
| R20 | 时区与场景 | 时间有明确时区；分派/提醒/升级/恢复名称正确；重试时生成时间不变 |

服务端 sanitizer 选型后再添加其真实解析器回归夹具，不能只 mock sanitize 返回值。
HTML/Markdown 中的外部 URL 验证使用发送替身；渲染和预览过程必须证明不发网络请求。

## 3. 配置、权限和并发测试

准备组织 A/B、普通用户 A/B、只读用户、策略编辑用户、模板管理员、超级管理员。

| ID | 场景 | 必须断言 |
|---|---|---|
| A01 | 新建多方式模板 | 主表与内容原子保存、类型唯一、revision=1 |
| A02 | 更新第二种方式失败 | 整个修改不生效，不保留部分新内容 |
| A03 | 两用户持同 revision 修改 | 一个成功，另一个 409；没有静默覆盖 |
| A04 | 组织 A 列表/详情/更新/删除访问 B | 无正文泄露；直接猜 ID 同样被拒绝 |
| A05 | 篡改 team、is_global、builtin_key | 普通用户不能扩大范围或伪造内置身份 |
| A06 | 全局模板 | 普通用户可按授权使用，只能超管管理全局自定义；内置对所有人只读 |
| A07 | 复制 B 的模板，或复制到无权组织 | 拒绝；合法复制产生独立模板、不继承引用和内置标记 |
| A08 | 预览真实告警 ID 属于 B | 拒绝；不接受客户端伪造 alert/team/raw_data |
| A09 | 只具策略编辑权的 options 查询 | 只返回可用摘要；不能藉此读模板正文/其他组织引用 |
| A10 | 无模板 View/Test 权限的直接 action 请求 | 拒绝，包括 retrieve、partial_update、preview、copy、test_send |
| A11 | 空授权组织、非法 cookie、子组织开关 | fail-closed；严格遵循已有组织工具语义 |
| A12 | 同时删除模板和新增引用 | 串行化成功或明确冲突，无悬空绑定 |
| A13 | 更新被引用模板时删除渠道内容/改变 scope/team | 拒绝破坏现有绑定；事务不产生索引漂移 |
| A14 | 解绑一个策略，多处仍引用 | 剩余引用正确，不能删除；引用计数按去重策略数 |
| A15 | 升级任务活动/结束 | 活动快照保护删除；结束释放；历史投递快照仍可追踪 |
| A16 | 列表/引用查询分页和 N+1 | 100 条分页上界；查询数不随行数线性增长 |
| A17 | 全局汇总绑定组织模板 | 拒绝；防止跨组织套用私有模板 |
| A18 | 相同组织范围并发创建同名模板 | 数据库唯一约束生效，返回受控冲突；排序差异不能绕过 |

真正依赖行锁的竞争测试须在受支持的事务数据库上验证；SQLite 单进程测试不能作为
PostgreSQL 并发语义已经通过的证据。本地不为常规测试启动整套中间件，事务数据库验证在
可用 CI/受控环境进行，无环境时记录待验证项。

## 4. 模板绑定与场景关联测试

| ID | 场景 | 必须断言 |
|---|---|---|
| B01 | 旧渠道数组无新字段 | 默认输出和选择语义不变 |
| B02 | default、场景缺失、场景 null | 缺失继承；null 显式默认；ID 使用指定模板 |
| B03 | 同类型两个渠道 ID 各选不同模板 | 内容独立，不按类型误继承另一渠道 |
| B04 | 邮件渠道引用仅有企微内容的模板 | 保存返回字段级错误 |
| B05 | 篡改渠道 type/name/ID、停用或不可见渠道 | 按可信渠道核验，不能绕过范围校验 |
| B06 | 提醒/升级/恢复覆盖 | 严格按实施文档优先级，默认和覆盖可观察 |
| B07 | 升级层渠道不存在于顶层 | 无显式模板用系统默认，不取其他渠道模板 |
| B08 | 新建升级任务后修改策略绑定 | 活动任务绑定快照不变；新任务使用新绑定 |
| B09 | 同一模板修改正文 | 后续新通知使用新 revision；已入队通知不变 |
| B10 | 层级渠道解析、重排、追加、替换 | 绑定跟随实际层和渠道，不凭数组 index 误关联 |
| B11 | 更新全局设置/策略失败 | 引用索引与父配置一起回滚 |
| B12 | Web 读取旧配置再保存 | 新模板字段与其他兼容字段不丢失 |

## 5. 通知生命周期、关联规则和完整链路测试

本节是本次必须补充的“相关性测试”。每条至少验证告警事实、实际模板选择、最终内容、
渠道数量和投递结果，不只断言某个 helper 被调用。

| ID | 入口与链路 | 必须断言 |
|---|---|---|
| C01 | 标准事件 → 即时规则 → 告警 → 自动分派 → 邮件/企微 | 两种正确正文、合法接收人；告警标题/内容未被通知模板改写 |
| C02 | 多事件 → 相关性聚合 → 单告警 → 分派 | 读取聚合告警快照、维度和富化；不误取任意首个 raw Event |
| C03 | 修改相关性规则的告警模板后生成新告警 | 通知中的 alert.title/content 随新告警事实变化，通知模板定义不被修改 |
| C04 | 同一告警改通知模板后新提醒 | 只改变通知表现；告警/事件/聚合 fingerprint/关联关系不变 |
| C05 | 富化成功/缺失/失败/历史数组后分派 | 成功变量准确，缺失有默认；富化失败不阻断基础告警通知 |
| C06 | 规则未命中、屏蔽或会话观察期 | 不产生原本不应产生的通知；模板不绕过 gating |
| C07 | 未认领提醒 + 当前升级层名单 | 收件人和模板匹配该层；提醒次数、频率和下次调度不变 |
| C08 | 升级 append/replace，两层不同渠道/模板 | roster 和层级内容正确；operator 原合同保留 |
| C09 | 自动恢复 + 勾 recovery + 用户目标 | 一次恢复通知、无重复恢复前缀、原提醒/升级按规则停止 |
| C10 | 自动恢复 + 组织目标 personnel=[] | 正确解析策略组织接收人，不静默漏发 |
| C11 | recovery 开启但重复提醒关闭 | 仍能通过可信持久关联找到分派策略；不重新猜测匹配规则 |
| C12 | 无关联策略或未勾 recovery | 保留原不发送语义 |
| C13 | 未分派即时报送/周期扫描 | 汇总模板选择正确，最多 10 条；无单一组织时继续跳过 OpsPilot |
| C14 | 人工分派、Incident、Monitor/Log 自有通知 | 原输出和参数默认值不变，不意外应用告警中心模板 |
| C15 | 渲染意外失败、默认回退成功 | 分派/恢复状态已提交，投递继续，记录 fallback 而非假称自定义成功 |
| C16 | 回退也失败，多渠道只有一个失败 | 该渠道持久失败，其他继续；告警主事务不回滚 |

C01/C02 用本地 fixture/可用本地聚合引擎串联真实模块，不启动生产 NATS 或采集代理。
若某条链路尚无可独立运行的 fixture，先建立可控输入与入口测试，不删掉验收项来适配现状。

## 6. Outbox、故障和混合版本测试

| ID | 场景 | 必须断言 |
|---|---|---|
| D01 | 模板版本/告警内容在入队后修改 | 重试参数逐字不变，仍使用原版本元数据 |
| D02 | 邮件成功、企微失败 | 仅企微重试；邮件 attempts 不变 |
| D03 | Broker 入队失败 | 意图仍持久存在，由周期补偿捞起 |
| D04 | worker 崩溃/租约过期后重领 | 旧 worker 不能覆盖新 claim 的终态 |
| D05 | 重试耗尽或不可重试内容错误 | 只失败本渠道，原错误分类清晰 |
| D06 | 同幂等键重复物化、重复试发请求 | 无重复渠道意图；请求 ID 参数不一致拒绝 |
| D07 | 数据库业务事务回滚 | 不产生外部发送；Outbox 与主事务一致 |
| D08 | 旧调用 → 新 SystemMgmt | 默认仍追加接收人；所有旧参数契约保留 |
| D09 | 新自定义调用 → 新 SystemMgmt | append_receivers=false 只影响正文，不丢实际接收人 |
| D10 | 旧 Outbox/已 delivered 父记录 | 不重新解释为新通知，不重放历史成功任务 |
| D11 | NATS 包装 | 只改 message；team/user_ids 来源可信；多告警无单一组织继续跳过 |
| D12 | 自定义 Webhook | 内容含引号/换行不破坏 JSON；请求结构仍由渠道控制 |
| D13 | 发布/回滚演练 | 接收端先兼容；队列排空前不回滚至不支持新字段的消费者 |

## 7. 日志、诊断与试发测试

| ID | 场景 | 必须断言 |
|---|---|---|
| O01 | 渲染失败写日志 | 稳定模板 + 独立参数；格式化结果有 ID/stage/type，无正文 |
| O02 | 异常带敏感哨兵 | 模板、告警原文、凭据、响应正文哨兵不出现在日志/错误响应 |
| O03 | 同一次失败多层经过 | 一处 traceback 所有权；返回值/异常身份/重试分类不变 |
| O04 | 默认回退发送成功 | UI 同时显示投递成功和“已使用默认模板”，不可混成发送失败 |
| O05 | 试发仅预览/未确认 | 无 Outbox、无渠道调用 |
| O06 | 试发身份/渠道/接收人篡改 | 权限拒绝；不能替任意用户或往未授权群发送 |
| O07 | 每用户/渠道速率超限 | 服务端拒绝；并发请求不能绕过共享计数 |
| O08 | 查询别人的测试 ID | 无结果泄露；管理员按明确权限查看 |
| O09 | 试发成功或失败 | 不修改真实告警状态、不污染其通知时间线与业务统计 |
| O10 | 群机器人试发 | 页面明确显示群级目标和确认步骤，不能标注“仅自己” |

## 8. Web 交互、Storybook 与视觉验收

建议新增 alarm-local 组件行为测试，以及 `alarm-notification-templates.stories.tsx`。

| ID | 交互 | 必须断言 |
|---|---|---|
| W01 | 有/无 View 权限进入配置 | 页签显示与路由权限一致；直接访问无权限路由不能读数据 |
| W02 | 新建/复制/编辑/查看内置模板 | 标题、可编辑字段、操作权限和请求一致 |
| W03 | 企微 → 邮件 → 企微切换 | 内容各自保留；格式与主题输入准确 |
| W04 | 编辑非当前 Tab 存在错误 | 保存被阻止并定位该 Tab，不只校验当前正文 |
| W05 | 在正文或标题光标位置插入变量 | 插入位置正确，保留选区外内容；实时预览正确 |
| W06 | 快速编辑引发多个异步预览 | 旧响应不覆盖新内容，错误/加载态不会卡住 |
| W07 | 真实告警切换及缺失变量 | 显示对应数据和 missing 提示，不保留前一告警内容 |
| W08 | HTML 恶意脚本、外部图片/样式、链接 | iframe 隔离且不加载外部资源，不导航父页面 |
| W09 | 策略渠道绑定、显式默认、场景继承 | 提交区分 null/缺失/ID，两个同类型渠道互不串内容 |
| W10 | 模板 revision 409、引用删除冲突 | 保留编辑内容，明确冲突，不显示假成功 |
| W11 | 离开未保存页面/删除方式 | 有明确提示；被引用格式不能删除 |
| W12 | 测试发送排队/成功/失败/限流 | 区分已入队与已送达，实际目标清晰，不重复提交 |
| W13 | 中英、亮暗、窄窗口 | 无硬编码主题色、遮挡或底部按钮不可达 |
| W14 | 表格分页/搜索/空/失败 | 真实调用、错误可重试、搜索与新建成组 |
| W15 | 通知时间线诊断 | 模板版本/场景/回退原因显示正确、敏感正文按权限读取 |

Storybook 至少包含：模板列表、空态、只读模板、Markdown 编辑、HTML 编辑、
缺失变量、格式错误、版本冲突、渠道绑定、试发确认、试发失败。
桌面视觉验收覆盖 1440/1024 宽度，窄窗口覆盖 736/360；小屏允许上下排列，不缩小文字硬塞两栏。

## 8.1 系统管理底层兼容测试（渠道探索补充）

依据 [channel-analysis.md](./channel-analysis.md)，重点验证“渲染业务内容”和“包装外部协议”
之间的接缝。不能把整个 `send_msg_with_channel` mock 掉后就宣称 HTML/Markdown 能正确送达。

| ID | 场景 | 必须断言 |
|---|---|---|
| S01 | Alerts HTML → RPC → send_msg_with_channel → SMTP 替身 | 解码 MIME 后是渲染后的原 HTML，MIME 类型为 text/html；没有被整体 escape |
| S02 | Alerts Markdown → 企微/钉钉 HTTP 替身 | payload 使用原平台外壳；正文保留用户 Markdown；格式标记未转为普通文本 |
| S03 | 飞书 title/content | header 与 Markdown element 正确；不能把正文 JSON 字符串误当完整卡片 |
| S04 | 同 Webhook body_template 接不同业务正文 | 请求结构保持渠道配置；正文替换一次；支持 Markdown/HTML 字符串 |
| S05 | Webhook 的正文为 JSON 字符串 | JSON 外壳仍合法，字符串不自动提升为对象；不二次解析告警占位符 |
| S06 | 旧调用含 receivers，新自定义关闭追加 | 旧 To 行保持；新正文精确；真实接收人不被清空 |
| S07 | dispatch_notification 既有调用 | 普通富文本 escape 契约保留；不得为 Alerts 改坏原调用方 |
| S08 | 预览、连通测试与模板试发 | 预览零外发；原连通测试仍固定消息；模板试发实际使用用户渲染内容 |
| S09 | 普通 NATS、事件副本、OpsPilot 各模式 | 各自协议不混用；仅 OpsPilot 模式绑定本次消息模板 |
| S10 | 共享发送入口收到其他业务的 HTML | 不套用 Alerts 模板校验/清洗/变量求值，不改变原 content 契约 |
| S11 | 系统管理有权限过滤而 Alerts 原候选查询不同 | 新候选/绑定独立验证组织权限，不从管理页过滤推定所有调用都安全 |
| S12 | 特定模板格式策略被拒绝 | 明确是 Alerts 编辑校验，不误报渠道不支持或修改全局渠道配置 |

## 9. 现有测试回归清单

以下文件已从当前工作区确认存在，实施时按改动范围执行，不把旧测试通过当新功能通过：

- `server/apps/alerts/tests/test_notify_params_format.py`
- `server/apps/alerts/tests/test_notify_dispatcher.py`
- `server/apps/alerts/tests/test_notify_result_service.py`
- `server/apps/alerts/tests/test_notification_delivery_service.py`
- `server/apps/alerts/tests/test_notification_log_security.py`
- `server/apps/alerts/tests/test_outbox.py`
- `server/apps/alerts/tests/test_outbox_extension_registry.py`
- `server/apps/alerts/tests/test_assignment_config_validation.py`
- `server/apps/alerts/tests/test_notification_target.py`
- `server/apps/alerts/tests/test_auto_assignment_chain.py`
- `server/apps/alerts/tests/test_reminder_service.py`
- `server/apps/alerts/tests/test_escalation_service.py`
- `server/apps/alerts/tests/test_escalation_assignment_flow.py`
- `server/apps/alerts/tests/test_recovery_notify.py`
- `server/apps/alerts/tests/test_un_dispatch_and_reminder_extra.py`
- `server/apps/alerts/tests/test_un_dispatch_nats_guard.py`
- `server/apps/alerts/tests/test_instant_alert_pipeline.py`
- `server/apps/alerts/tests/test_enrichment_downstream_service.py`（当前工作区已有，尚未提交）
- `server/apps/system_mgmt/tests/test_slice_channel_utils.py`
- `server/apps/system_mgmt/tests/test_nats_api_handlers_service.py`
- `server/apps/rpc/tests/test_system_mgmt_forwarding.py`
- `server/apps/system_mgmt/tests/test_channel_viewset_team_permission.py`
- `web/scripts/alert-assignment-notification-target-test.ts`
- `web/scripts/alarm-notification-tooltip-test.ts`

修改共享 CodeEditor、RPC 或渠道函数后，补充受影响调用者的兼容测试，而不是仅测 Alerts。

## 10. 验证执行与证据

实施阶段先读取 `DEVELOP.md`、Server 测试指南和 Web 本地 Next.js 文档，核对可用依赖。
常规 Server 单测使用 SQLite，不为单测启动整套 Postgres/Redis/NATS。

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest <本次新增及受影响的测试路径> --no-cov
```

```bash
cd web
pnpm exec vitest run <本次新增组件测试路径>
pnpm lint
pnpm type-check
```

上面是待执行命令模板，不是已运行记录；占位路径在实施时替换成真实路径。
另外验证：模型迁移无遗漏与冲突、菜单/权限登记、中英文键、Storybook 构建或目标故事可访问、
共享组件归属检查，以及方案中必须在事务数据库/真实渠道执行的验收。

验收记录格式：

| 日期/代码状态 | 测试 ID | 命令或手工操作 | 结果 | 原始证据/限制 |
|---|---|---|---|---|
| 未执行 | 全部 | 等用户明确授权实施 | 待实施 | 本轮仅测试设计 |

- 不记录真实凭据、群 Webhook、SMTP 密码或私人消息内容作为证据。
- 无法运行/基线失败保留原始错误和影响范围，不能标成通过。
- 真实渠道验收最少一封 HTML 邮件、一条企微 Markdown 消息，由用户确认目标后进行。
- 交付时所有 P0（组织隔离、渲染安全、生命周期不回滚、Outbox 重试）必须通过；其余未验收项
  显式列出，不以原型截图代替正式页面或渠道验证。
