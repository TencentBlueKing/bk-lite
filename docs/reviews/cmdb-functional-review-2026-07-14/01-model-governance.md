# CMDB 模型治理生产级审查

## 1. Summary

模型治理以 HTTP ViewSet 为入口：分类与模型主体写入 FalkorDB；字段分组、公共枚举库写入 Django ORM；唯一规则存放在 `MODEL.unique_rules` JSON；自动关联规则存放在 `MODEL_ASSOCIATION.auto_relation_rule` 边属性；展示字段同时存在于模型 `attrs` 与实例冗余属性。社区层通过 `model_ops` 注册表委派企业字段类型规则；HEAD 已通过 `enterprise` gitlink 和 `.gitmodules` 声明 Enterprise 子模块，但本 worktree 未初始化该子模块，因此本域只完成社区委派契约审查，overlay 行为验证仍是未完成范围。

主模型 CRUD、模型关联创建/删除、字段新增/更新已有菜单权限和部分对象权限；规则校验也能拒绝字段不存在、类型不一致、展示字段及不支持类型。不过，模型子资源、自动关联双端授权和公共枚举租户边界没有保持同一权限契约；字段分组、公共枚举传播与布局保存也缺少可收敛的跨存储状态机。

本域确认 7 个主 Finding：P0 1 个、P1 4 个、P2 2 个；没有 P3。P0 `CMDB-F04` 会把部分失败任务错误标记为成功且没有恢复闭环，优先级高于其余权限与一致性问题。Recommendation 为 **Request changes**。

## 2. Findings

### Finding CMDB-F04：公共枚举传播把部分失败标记为成功且不可恢复

- Severity: P0
- Location: `server/apps/cmdb/services/public_enum_library.py:82-126,191-301`；`server/apps/cmdb/tasks/celery_tasks.py:359-364`
- Root cause category: 状态机设计缺陷
- Evidence: `update_library` 先保存 ORM options，再同步调用 Celery `.delay()`，没有 `transaction.on_commit`、持久化 outbox 或周期恢复；broker 失败会在库已提交后返回错误。Worker 全量扫描模型，单模型图写异常只追加 `failed_items`，最终仍返回 `result=True`；`sync_public_enum_library_snapshots_task` 原样返回该结果，Celery 将存在失败副作用的任务标记为成功且不会重试。成功分支只更新模型 `attrs.option`，未调用实例 `_display` 重建，因此选项改名后既有实例继续保留旧显示名。
- Trigger: broker 派发失败、任一模型图写暂时失败，或公共选项 ID 不变但名称变化。
- Impact: 公共库、不同模型的枚举快照和实例可搜索展示值可永久处于不同版本；API/任务状态又无法指出待恢复对象，搜索和展示会返回旧含义。
- Why existing tests missed it: `test_update_library_options_enqueues` 将 enqueue 替换为布尔标记；`test_sync_library_snapshots_ok` 只断言模型 `set_entity_properties` 被调用，没有 broker 失败、部分图失败、重投、任务终态或实例 `_display` 断言。
- Minimal safe fix: 库更新与持久化传播事件同事务提交；Worker 以模型/字段为可重试单元记录状态，失败抛出或进入可恢复终态；模型快照成功后按受影响模型/字段分页重建实例 `_display`。
- Required tests: 覆盖 broker 首次失败后恢复、单模型失败重试、重复投递幂等、部分成功不报 SUCCESS、选项改名后实例展示值更新，以及大批量分页/资源上限。
- Long-term design note: 将公共枚举视为版本化主数据，用 durable outbox + per-consumer checkpoint 驱动模型快照和实例投影，禁止以一次 fire-and-forget 全量扫描表达一致性。

### Finding CMDB-F01：模型唯一规则与字段分组缺少模型对象权限

- Severity: P1
- Location: `server/apps/cmdb/views/model.py:649-695`；`server/apps/cmdb/views/field_group.py:37-185,243-360`
- Root cause category: 跨层契约不一致
- Evidence: 模型主体的更新、删除会调用 `organizations` 和 `has_object_permission(OPERATE)`；唯一规则四个 handler 仅有菜单级 `HasPermission`，直接把 URL 的 `model_id` 交给 Service。字段分组除 `full_info` 外，列表、详情、创建、改名、删除、移动、批量迁移和排序同样只做菜单权限，并按 ORM 主键或请求中的 `model_id` 操作。
- Trigger: 拥有 `model_management-View/Edit Model/Delete Model` 菜单权限、但没有目标模型组织/实例权限的用户，请求其他组织模型的唯一规则或字段分组接口。
- Impact: 攻击者可读取其他组织模型字段元数据，修改唯一性规则使实例写入被错误拒绝或放宽，并可重排、迁移或删除字段分组；模型主体对象权限被子资源接口绕过。
- Why existing tests missed it: `test_unique_rule_crud.py` 直接测试 Service，且 Mock 掉模型查询、实例查询和图保存；`test_field_group_service.py` 直接调用 Service；`test_model_views.py` 的唯一规则用例使用 superuser 并 Mock Service。没有受限用户、跨组织模型和拒绝路径断言。
- Minimal safe fix: 为所有模型子资源建立统一的 `require_model_view_permission` / `require_model_operate_permission` 门面；字段分组按 `group.model_id` 反查模型后授权，禁止仅依赖 ORM 主键和菜单权限。
- Required tests: 增加唯一规则 GET/POST/PUT/DELETE 与字段分组所有读写 action 的同组织允许、跨组织 403、默认组织语义和拒绝路径零 Service/零图写测试。
- Long-term design note: 模型下属资源应由一个对象授权网关统一解析 `model_id`、组织和操作级别，避免每个 View 重复并逐渐漂移权限逻辑。

### Finding CMDB-F02：自动关联规则只校验关联一端权限

- Severity: P1
- Location: `server/apps/cmdb/views/model.py:395-495`；`server/apps/cmdb/services/model.py:1524-1664`
- Root cause category: 跨层契约不一致
- Evidence: 模型关联创建在 View 中分别校验源、目标模型的 OPERATE 权限；自动关联规则的新增、修改、删除只校验 URL 中一个 `model_id`。Service 仅要求该 ID 属于关联任一端，随后修改整条关联边属性并调用 `schedule_rule_auto_relation_full_sync([model_asst_id])`。
- Trigger: 用户拥有关联一端模型的 OPERATE 权限，但没有另一端模型权限；以有权限的一端作为 URL `model_id` 保存或删除自动关联规则。
- Impact: 单侧模型操作者可读取双端字段、改变整条关系的匹配规则并触发涉及无权限模型实例的全量关系重建，突破关联创建时的双端授权契约。
- Why existing tests missed it: `test_model_service_advanced.py` 只验证关联存在、`model_id` 属于任一端和图方法调用；`test_auto_relation_rule_validate.py` 只验证 payload/字段类型。没有 View 层双模型权限矩阵或拒绝后零调度断言。
- Minimal safe fix: 规则 GET 要求双端 VIEW，新增/修改/删除要求双端 OPERATE；授权必须在读取字段和调度全量同步之前完成。
- Required tests: 覆盖源有权/目标无权、目标有权/源无权、双端有权、关联不存在，并断言拒绝路径不读取另一端字段、不写边、不调度同步。
- Long-term design note: 把“关联资源授权”抽象为以关联 ID 为入口的双端授权器，关联 CRUD、规则 CRUD 与关系同步共用同一契约。

### Finding CMDB-F03：公共枚举库可跨组织修改和删除

- Severity: P1
- Location: `server/apps/cmdb/views/public_enum_library.py:20-109`；`server/apps/cmdb/services/public_enum_library.py:45-150,208-233`
- Root cause category: 跨层契约不一致
- Evidence: 列表调用 `list_libraries(team=team)` 后仍返回全部库，只计算 `editable` 展示标记；更新和删除只做菜单权限，Service 按 `library_id` 直接取对象写入或删除，未校验 `library.team`。创建还直接接受调用方提供的任意 `team`。
- Trigger: 有模型编辑/删除菜单权限的用户枚举或猜中其他组织的 `library_id`，直接调用 update/destroy；或创建时提交未授权组织 ID。
- Impact: 可读取其他组织枚举内容，跨组织改名、改选项、转移团队或删除未被模型引用的库；引用该库的模型配置随后会被异步改写。
- Why existing tests missed it: `test_public_enum_service.py` 明确把不同 team 的库返回并只断言 `editable=False`，所有更新/删除均直接调用 Service；没有 View 层组织授权和越权零写入测试。
- Minimal safe fix: Service 接受并强制授权组织范围；列表只返回公共库或授权组织交集，写入/删除要求库 team 属于授权范围，创建/转移 team 校验提交集合是授权集合子集。
- Required tests: 增加跨组织 list 不可见、update/delete 403、任意 team 创建/转移拒绝、公共库策略、include_children 与拒绝路径数据库不变测试。
- Long-term design note: `editable` 只能是服务端授权结果的展示，不能替代查询集裁剪和写路径强制校验；公共枚举应复用统一 JSON 组织范围 helper。

### Finding CMDB-F05：SQLite 字段删除在图删除后固定失败

- Severity: P1
- Location: `server/apps/cmdb/services/model.py:1198-1258`；`server/apps/cmdb/views/model.py:616-622`
- Root cause category: 局部实现错误
- Evidence: Service 先从 FalkorDB 模型 `attrs` 删除字段并从全部实例移除属性，然后 View 使用 `FieldGroup.objects.filter(..., attr_orders__contains=attr_id)` 清理 ORM JSONField。SQLite 不支持该 lookup。现有 `test_model_attr_delete_ok` 在显式 SQLite 环境实跑失败，异常为 `django.db.utils.NotSupportedError: contains lookup is not supported on this database backend`，定位 `views/model.py:619`。
- Trigger: SQLite 部署中删除任一非保护字段，且请求到达字段分组清理语句；即使分组中没有该字段，查询编译也会失败。
- Impact: 接口返回 500，但字段定义和所有实例值已从 FalkorDB 删除，FieldGroup 仍残留旧字段 ID；调用方可能重试，审计/外部结果与真实图状态不一致。
- Why existing tests missed it: 简报六文件套件不包含 `test_model_views.py`，因此结果为 102 passed；单独运行现有字段删除用例立即失败。该用例还 Mock 了 `delete_model_attr`，未断言 500 前图侧已经发生不可逆删除。
- Minimal safe fix: 使用跨数据库 JSON membership helper 或有界 Python 过滤更新相关分组；更关键的是在图删除前完成所有可失败校验，并为图/ORM删除建立可补偿状态或幂等恢复。
- Required tests: 在 SQLite 上执行真实 FieldGroup 清理，断言响应成功和 `attr_orders` 更新；模拟 ORM 清理失败，断言不会产生“图已删/ORM 未清”的不可恢复结果；在支持 JSON contains 的数据库做契约一致性测试。
- Long-term design note: 字段删除应是一个持久化 operation：预检引用、记录意图、幂等执行图清理和 ORM 投影、最终收敛，而不是在 View 中追加第二次存储写入。

### Finding CMDB-F06：字段分组双存储变更缺少补偿

- Severity: P2
- Location: `server/apps/cmdb/services/field_group.py:69-137,140-199,391-556`
- Root cause category: 状态机设计缺陷
- Evidence: 分组改名先 `group.save()` 再更新 FalkorDB `attrs.attr_group`，图写失败时 ORM 新名已提交；批量/单字段迁移先写 FalkorDB，再逐个更新 ORM `attr_orders`，ORM 失败时图已提交。`delete_group` 虽使用 `transaction.atomic()`，其中的 FalkorDB 写不受 Django 事务回滚控制。
- Trigger: 任一后半段图连接、ORM 保存或进程执行失败；也可由数据库约束/连接中断在第一套存储提交后触发。
- Impact: 分组列表、模型字段分组和分组内排序互相矛盾；后续读取会丢字段、重复展示或把字段放入不存在的分组，接口只返回错误而没有恢复入口。
- Why existing tests missed it: `test_field_group_service.py` 的成功用例使用 Fake Graph 并断言调用；没有在第一套存储成功后注入第二套存储失败，也没有重新读取两套存储验证回滚/恢复。
- Minimal safe fix: 在操作前保存两侧快照并对后半段失败执行显式补偿，或至少记录 durable operation 由幂等 Worker 收敛；不得把 `transaction.atomic()` 当作图事务。
- Required tests: 分别注入 ORM-first/Graph-second 和 Graph-first/ORM-second 失败，验证最终两侧恢复原值或进入可查询、可重试的明确状态；覆盖进程在两步之间崩溃后的恢复。
- Long-term design note: 明确 FalkorDB `attrs.attr_group` 为主数据、FieldGroup 为投影，或反之；所有分组变更只写主数据并通过 outbox 投影，消除双主写入。

### Finding CMDB-F07：布局保存只回滚分类，模型部分写不回滚

- Severity: P2
- Location: `server/apps/cmdb/views/model.py:143-170`；`server/apps/cmdb/services/classification.py:136-184`；`server/apps/cmdb/services/model.py:1864-1896`
- Root cause category: 状态机设计缺陷
- Evidence: `save_layout` 仅快照分类；分类先逐项更新，模型随后逐项查询和写入。模型中途失败时只调用分类快照回滚，已经成功写入的前序模型不会恢复。代码注释把“用户重试可重新应用”当作安全性，但接口返回 500 后没有自动重试或待恢复状态。
- Trigger: 提交至少两个模型的布局，前一模型写成功、后一模型 `set_entity_properties` 抛错。
- Impact: 分类回到旧布局，部分模型留在新布局，所有用户在调用方是否手工重试之前看到混合排序/可见性；失败请求的外部语义不是原子保存。
- Why existing tests missed it: `test_reverts_classifications_when_model_update_fails` 把整个 `update_model_orders` Mock 为“调用即抛”，只证明模型写开始前的分类回滚；没有模拟第二个模型失败并核对第一个模型的实际值。
- Minimal safe fix: 在任何写入前同时快照分类和模型，并在失败时对两侧执行补偿；补偿失败必须记录待恢复状态并由后台重试，不能只重新抛异常。
- Required tests: 真实 Fake Graph 记录第二项失败，断言分类和第一项模型均恢复；再覆盖回滚本身失败、重复提交幂等及不存在 ID 的明确错误契约。
- Long-term design note: 将布局保存设计为带 revision 的整包配置或持久化 operation，以 compare-and-swap/幂等应用取代跨多节点的裸循环写。

## 3. Test Review

简报原始命令首次在沙箱内因 `~/.cache/uv/sdists-v9/.git` 无权限退出 2；受控重跑进入 102 项收集，但因默认 PostgreSQL `DB_NAME=None` 得到 `23 passed, 79 errors`。补充 `SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb_task2_review.sqlite3 ENABLE_CELERY=true` 后，同一六文件套件最终 **102 passed in 2.83s，exit 0**。简报未要求 `--cov`，本次没有可信覆盖率数字，不能声称达到 80%/90% 目标。

有效证明包括：分类 CRUD 与使用中保护；唯一规则候选、条数和字段组合；自动关联字段存在性、类型一致性、不支持类型和展示字段拒绝；字段分组基本 CRUD/排序/字段归属；公共枚举 options 校验、引用删除保护和模型快照成功写入。

证明力不足包括：

- 大量 Service 测试用 monkeypatch/Fake Graph 替代真实图状态，唯一规则成功用例甚至 Mock `_save_unique_rules`，无法证明写入、失败传播或权限。
- 公共枚举测试只证明 enqueue 被调用和模型属性被设置，不证明 durable delivery、部分失败重试和实例 `_display` 收敛。
- 自动关联测试不经过双端对象权限和全量同步外部效果。
- 字段分组测试没有跨存储失败注入；布局原子性测试在模型第一笔写之前抛错。
- 现有 `test_model_attr_delete_ok` 在 SQLite 下单独实跑 **1 failed in 2.26s，exit 1**，直接复现 CMDB-F05；六文件绿灯没有覆盖该入口。
- Enterprise 扩展仅验证社区注册表默认实现与自定义 stub；HEAD 存在 `enterprise` gitlink 与 `.gitmodules`，但本 worktree 未初始化子模块，overlay 源码在本次审查环境不可用。附件/图片真实校验、导入导出和审计委派属于未完成范围，不能从社区门面测试外推结论。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：部分可以。主模型 Service 边界可追踪，但权限散落在 View，字段分组和公共枚举又各自绕开对象授权，维护者难以推断真实安全边界。
2. 新增同类插件是否需要复制代码：Enterprise 字段类型扩展不需要，注册表契约较清晰；新增模型子资源仍会复制权限、图/ORM双写和错误处理。
3. 新增错误类型是否需改多个模块：是。View 将部分 `BaseAppException` 手工映射为 400/404/409，异步任务又用 `result=True/failed_items` 表达失败，没有统一 error mapper。
4. 新增 callback 模式是否容易扩展：本域没有外部 callback；公共枚举传播只有直接 Celery 调用，没有 durable event 契约，增加消费者会复制扫描和失败逻辑。
5. 当前接口是否容易被误用：是。Service 接受裸 `model_id/library_id` 而不接授权上下文；`editable` 容易被误认为安全控制；`transaction.atomic()` 容易被误认为覆盖图写。
6. 日志是否足够且不泄密：基本不泄露凭据，但批量失败只留非持久化日志和返回值，没有 operation/task 状态供关联排障。
7. 状态异常时能否判断停在哪个阶段：不能。布局、字段分组和公共枚举都没有阶段、版本、重试次数或待恢复实体记录。
8. 设计是否降低复杂度：规则 dataclass/校验器和 Enterprise 门面降低了局部复杂度；双主存储裸写与分散授权只是把一致性和安全问题移动到 View、Celery 和人工重试。

## 5. Recommendation

**Request changes**。

`CMDB-F04` 是发布阻断项：必须先消除任务错误成功，建立可恢复投递、部分失败重试和实例展示收敛，再评估进入生产。其后至少关闭三个 P1 权限根因（模型子资源、关联双端、公共枚举组织边界）并修复 SQLite 字段删除。P2 的字段分组与布局跨存储状态也应在进入生产前提供补偿或持久化恢复机制；仅增加成功路径 Mock 测试不足以降低风险。
