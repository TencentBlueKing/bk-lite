# 部署时生成 Default 组织的默认策略组

Status: implemented — 2026-11-18

2026-11-18 修订：策略组搜索的清除使用本次输入值，不再读尚未更新的搜索状态。列表在默认指针还在、组已被删时返回 `default_removed`，空状态改为「默认组已删除，之后新实例不再自动告警」，不再承诺接入时会重新生成。

实测证据：

- sqlite：`INSTALL_APPS=`（避开本机 `.env` 里不含 cmdb 的 `INSTALL_APPS`，否则 monitor 启动导入 cmdb 模型失败）、`DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/monitor/tests/test_init_default_policy_groups.py apps/monitor/tests/test_policy_group_service.py apps/core/tests/test_batch_init_command.py apps/monitor/tests/test_policy_group_views.py --nomigrations --no-cov -o addopts=` → `124 passed in 7.27s`。
- web：改动文件 eslint 通过；vitest 3 个文件 `7 passed`；`pnpm type-check` 通过。
- 本机 Postgres 已运行。`plugin_init` 耗时 real 23.26s，策略模板对账创建 809、更新 92、删除 39。内置模板 773 条、33 个对象，变为 1537 条、48 个对象。
- 第一轮 `init_default_policy_groups`：`created=0 skipped=8 failed=40`。40 个对象都失败在 `MonitorPolicyViewSet.format_crontab` 的 `CrontabSchedule.objects.get_or_create`，异常为 `MultipleObjectsReturned`。`CrontabSchedule` 没有唯一约束，本机已有同值重复行（`*/5` 3 行、`*/30` 2 行）。事务回滚，没有留下半个组。这个缺陷同样会让首次需要时生成默认组、手工保存策略失败。
- 修复：`format_crontab` 改为取同值最早一行，没有再新建（`server/apps/monitor/views/monitor_policy.py`），并补重复行、缺失两条回归测试（`test_monitor_policy_view_helpers.py`）。sqlite 回归共 `166 passed`。
- 修复后本机 Postgres：首次 real 45.18s，`created=40 skipped=8 failed=0`；第二次 `created=0 skipped=48 failed=0`。Default（id=1）组 48、指针 48、规则 1507；Guest、虚拟团队组数 0。`PolicyGroupMembership` 前后都是 3。启用的扫描任务 22 个，全部属于原本已有成员的两个组，新生成的组没有启用任何扫描任务。
- 未修：`server/apps/log/views/policy.py` 的 `format_crontab` 有同样写法，不在本规格范围。
- 本机全链路（2026-11-18，`server/.env.local` 环境）：`batch_init --apps=monitor` real 21.58s，`plugin_init` 后输出 `created=0 skipped=48 failed=0`，无告警。浏览器（`next dev` + 8443 后端热重载）：MSSQL、交换机出现「MSSQL默认告警」「Switch默认告警」（实例 0）；Consul 显示新空状态文案。临时建子组织（Default 下）和两台测试实例并打开「包含子组织」后：
  - 加入实例抽屉里两台子组织实例都不可勾选，分别显示「属于其他组织」「已在 Host默认告警（只读）」。
  - 实例详情「监控策略」显示「在组 · Host默认告警（策略组验证子组织）」和切换组织提示，没有更换和退出按钮；当前组织实例仍显示更换、退出。
  - 关闭「包含子组织」后 `membership` 仍返回「实例不属于当前组织」；子组织实例 `join` 到 Default 组被拒。
  - 验证后测试数据已删除，Default 组 48、成员 3、Default 组内启用扫描任务 22，无孤儿任务。

## Problem Statement

默认策略组现在只在某个组织第一次需要时生成：打开接入页拉策略组列表，或节点管理新建、CMDB 首次对上一条实例。部署只把各插件的 `policy.json` 对进内置策略模板，不建组。策略组页面带 `create_default=false`，只浏览不会建组。

结果是部署完成后，策略组页面几乎是空的。本机 50 个监控对象里只有 8 个有默认组，Switch 有 243 条内置模板、1 台实例，组仍是 0。用户以为初始化漏了。

另有两处跟组织相关的显示问题：

- 父组织勾上「包含子组织」后，实例详情的策略页调用 `membership`，后端返回「实例不属于当前组织」，前端吞掉错误，策略组栏整块不显示。
- 策略组「加入实例」弹窗会列出子组织的实例。`instance_groups` 只按当前组织查，这些实例的所属策略组显示「未加入」，勾选后加入会被后端拒绝。

## Solution

`plugin_init` 完成后，为 Default 组织按监控对象生成默认策略组。策略组仍只属于一个组织，按监控对象建，规则记住插件。其他组织和子组织保持现有的「第一次需要时生成」。

子组织的实例在父组织视图里只读显示它在自己组织里的策略组，不能在父组织里加入、更换或退出。

策略组页面在当前组织还没有任何组时给出说明。

## User Stories

1. 作为管理员，全新部署完成后打开策略组页面，就能看到 Default 组织下每个有内置模板的监控对象的「对象名默认告警」，不用先去接入页。
2. 作为管理员，重启或升级服务后，已经生成的默认组不重建、不改名、不增删规则。我删掉的默认组不会被重新生成。
3. 作为管理员，升级前就已经存在的实例不会因为这次部署被加入默认组。
4. 作为子组织的运维，我第一次在自己的组织里接入实例时，生成的是我自己组织的默认组，与 Default 的组互不影响。
5. 作为父组织的运维，我勾上「包含子组织」后，在实例详情里能看到子组织实例所在的策略组，并被提示要切到那个组织修改。
6. 作为父组织的运维，在「加入实例」弹窗里不能勾选子组织的实例，也能看到它们已在哪个组。
7. 作为运维，打开一个还没有任何策略组的对象时，页面告诉我默认组会在接入实例时生成。

## Implementation Decisions

### 1. 部署初始化命令

- 新增管理命令 `server/apps/monitor/management/commands/init_default_policy_groups.py`。
- Default 组织：`GroupUtils.active_queryset(name="Default", parent_id=0).order_by("id").first()`（`apps.system_mgmt.utils.group_utils`）。找不到时记一条 WARNING（`event=policy_group_default_init_skipped reason=default_organization_missing failed_stage=resolve_organization`），命令正常返回，不建组。
- 只处理 Default。Guest、虚拟团队、其他业务组织和子组织都不处理。
- 遍历范围：有内置模板（`PolicyTemplate.template_type=builtin`）的监控对象，按 id 排序。没有内置模板的对象不进入遍历。
- 每个对象调用现有 `PolicyGroupService.ensure_default(organization=<Default id>, monitor_object=<对象>, operator="system")`，不另写生成逻辑：
  - 已有 `PolicyGroupDefault` 指针，包括指向空的指针（用户删掉了默认组），跳过。
  - 没有指针，用该对象当前全部内置模板建一个系统组并写指针。成员为空；规则对应的扫描任务由 `ensure_scan_task` 创建后保持关闭。
  - 多个副本同时启动时，`ensure_default` 已有的行锁和 `IntegrityError` 回退保证只生成一份。
- 计数在调用前后按指针判断：`created`（本次新写指针）、`skipped`（调用前已有指针）、`failed`。
- 单个对象失败：捕获异常，`logger.exception("event=policy_group_default_init_failed organization=%s monitor_object_id=%s failed_stage=ensure_default error_type=%s", ...)`，继续下一个对象。这是这次失败唯一的 traceback 所有者。`ensure_default` 内部的事务保证失败对象不留下半个组。
- 结束时一条 INFO 汇总：`event=policy_group_default_init_finished organization=%s created=%s skipped=%s failed=%s`。逐个对象的结果最多到 DEBUG。
- 日志用 `from apps.core.logger import monitor_logger as logger`，模板加惰性参数，不记模板正文、策略配置或异常正文以外的 payload。
- 不触碰成员：不调用 `consider_auto_join`、`join` 或任何成员写入，存量实例保持无记录。

### 2. 接入 batch_init

- `server/apps/core/management/commands/batch_init.py` 的 `_init_monitor` 在 `call_command("plugin_init")` 之后调用 `call_command("init_default_policy_groups")`。
- `plugin_init` 抛错时不进入这一步，沿用现有失败语义。
- `init_default_policy_groups` 整体抛错（例如数据库瞬断）不阻断启动：照搬 `_init_system_mgmt` 里 `init_notification_tags` 的写法，`except Exception` 记 WARNING（`event=policy_group_default_init_failed failed_stage=init_default_policy_groups error_type=%s`，`exc_info=safe_exception_info(error)`），stdout 只写异常类型和「可运行 init_default_policy_groups 重试」，不写异常正文。下次启动会补上未完成的对象。
- 这一步只读写本地数据库：策略组、监控策略、`PolicyOrganization`、`PeriodicTask` / `CrontabSchedule`。不依赖 Celery Worker、Beat、NATS 或任何 Supervisor 管理的进程，符合 `docs/operations/server-startup-dependencies.md` 的启动期约束。实施前按 AGENTS.md 读该文档确认。

### 3. 子组织实例只读显示

后端 `server/apps/monitor/views/policy_group.py`：

- `membership`：实例属于当前组织时保持现有返回不变。实例不属于当前组织、但属于 `scope.data_team_ids`（即勾了「包含子组织」后可见）时，返回只读结果：
  - `read_only: true`
  - `state`、`group_id`、`group_name` 按实例自己的成员记录返回
  - `group_organization`：所属策略组的组织 id，`group_organization_name`：该组织名称（未入组时为空）
  - `groups: []`、`templates: []`；`legacy_policies` 照常返回
  - 实例连 `data_team_ids` 都不在时，保持原错误「实例不属于当前组织」。
- 现有返回补一个 `read_only: false`，其余字段不变。
- `instance_groups`：可见范围从当前组织改为 `scope.data_team_ids`。每行增加 `group_organization` 和 `read_only`（策略组的组织不等于当前组织时为 `true`）。`PolicyGroupService.member_group_names` 相应改成接收组织集合；当前组织的调用方结果不变。
- `join`、`leave` 等写接口不放宽，子组织实例仍被拒绝。

前端：

- `web/src/app/monitor/(pages)/view/monitorPolicy.tsx`：`read_only` 时显示状态徽标和组名，不显示加入、更换、退出按钮，提示文字为「这台实例属于其他组织，策略组请切换到所属组织后修改」。组名后可带上所属组织名称。
- `web/src/app/monitor/(pages)/event/policy-group/page.tsx` 的「加入实例」弹窗：候选实例的 `organization` 不包含当前组织（`current_team` cookie）时，复选框不可用，「所属策略组」一列显示「属于其他组织」，已在组时显示「已在 <组名>（只读）」。
- 布局用 Tailwind 与现有组件，颜色只用语义 token，不新增 SCSS。

### 4. 策略组页面空状态

- `page.tsx` 在选中某个监控对象、没有搜索条件、列表为空时，表格空状态显示：「当前组织还没有这个对象的策略组。接入这个对象的实例时，会自动生成默认策略组；也可以从策略模板新建。」有搜索条件时保留现有空状态。
- 不改列表请求里的 `create_default=false`。

### 5. 文档

- `docs/design/product-decisions/monitor-policy-group.md` 的「已确认设计决策」补三条：Default 在部署时按对象生成默认组，其他组织第一次需要时生成；策略组只属于一个组织，不做多组织绑定；「包含子组织」只放大查看范围，子组织实例的策略组只读。「已替代决策」记一条：2026-11-18 起 Default 组织不再等首次需要才生成默认组。
- 本 spec 的 Status 改为 implemented，并写明实测证据。
- 不改 `openspec/`。

## Testing Decisions

服务与命令（新文件 `server/apps/monitor/tests/test_init_default_policy_groups.py`，sqlite）：

- Default 存在，两个对象有内置模板、一个没有：生成两个系统组、两条指针；没有模板的对象没有组也没有指针。规则数等于各对象内置模板数，对应扫描任务都是关闭的。
- 连跑两次：组、规则、指针数量不变，第二次汇总为 `created=0`。
- 默认指针指向空（用户删过默认组）：不重新生成。
- Guest 组织和另一个业务组织：不生成任何组。
- 启动前已有的实例：没有新增 `PolicyGroupMembership`。
- 一个对象的 `ensure_default` 抛错（monkeypatch）：其余对象照常生成，命令不抛错；失败日志模板与参数分开、完整格式化输出含 `failed_stage=ensure_default` 和 `error_type`，只出现一条带 traceback 的记录；敏感哨兵字符串不出现在日志里。
- Default 不存在：记 WARNING，不建组，不抛错。

batch_init（`server/apps/core/tests/test_batch_init_command.py`）：

- `monitor` 模块的命令序列更新为 `["plugin_init", "init_default_policy_groups"]`。
- `plugin_init` 失败时不调用 `init_default_policy_groups`（现有失败用例的断言随之核对）。
- `init_default_policy_groups` 抛错时 `batch_init` 继续后续模块，stdout 有跳过提示。

接口（现有策略组视图测试文件，或新增）：

- 当前组织实例的 `membership` 返回与原来一致，外加 `read_only: false`。
- 子组织实例在 `include_children` 打开时返回 `read_only: true`、正确的组名和组织；关闭时仍是原错误。
- `instance_groups` 对子组织实例返回其所在组和 `read_only: true`；当前组织实例结果不变。
- 子组织实例调用 `join` 仍被拒绝。

前端：

- 只读判断和候选行禁用逻辑若抽成纯函数，放到对应 `__tests__` 下用 vitest 覆盖。
- 对改动文件跑 eslint，并跑 `pnpm type-check`。

命令：

- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/monitor/tests/test_init_default_policy_groups.py apps/monitor/tests/test_policy_group_service.py apps/core/tests/test_batch_init_command.py <策略组视图测试> --nomigrations --no-cov -o addopts=`
- `cd web && pnpm exec vitest run <新增测试>`、`pnpm exec eslint <改动文件>`、`pnpm type-check`

本机真实环境（`make -C deploy/local dev-ps` 确认 Postgres 已起）：

1. 先跑一次 `plugin_init`，让本机内置模板追平磁盘（本机模板表上次对账是 2026-08-17，MSSQL、VM 当前为 0 条）。
2. 跑 `init_default_policy_groups`，用 Django ORM 或 psql 只读查询核对：Default（本机 id=1）下有内置模板的对象各有一个默认组，Guest 和虚拟团队为 0；记录首次耗时和生成的规则数。
3. 再跑一次，确认数量不变、汇总 `created=0`。
4. 运行前先记下 `PolicyGroupMembership` 总数，运行后不变。

## Out of Scope

- 插件升级后，把新增的内置模板补进已经生成的默认组。需求 `p398_826` 列为本期不做，保持后置。
- 把存量实例自动加入默认组。仍由用户在策略组「实例管理」或实例页手动加入。
- 为 Guest、虚拟团队、其他业务组织或子组织在部署时预生成默认组。
- 一个策略组绑定多个组织，或在父组织里修改子组织的策略组。
- 改接入页、节点管理和 CMDB 的自动加入规则。
