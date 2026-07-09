# projectmem - bk-lite

_Last updated: 2026-07-09_

## Project purpose
BK-Lite is an AI-first lightweight operations platform for operations administrators. It combines a Django business backend, Next.js control consoles, mobile/desktop shells, distributed collection agents, and algorithm services to provide CMDB, monitoring, alerting, log, job, node, MLOps, and OpsPilot capabilities with low deployment cost and progressive operational workflows.

## Recent issues
- [DONE] #0010 本 plan「采集频率默认 60s」漏了 285 个 plugin UI.json 的 form default_value=10(仅 interval 字段,已脚本验证),导致前端创建任意类型监控实例表单仍默认 10s。spec grep 只搜了 .py/.yaml/.go/.toml,完全没覆盖 .json。根因:插件 UI.json 的 form_fields[*].default_value 才是前端页面渲染的"默认值",跟 Django 模型 default 无关。需另开 plan 全量改 285 个文件 + 跑 server migrate。 [server/apps/monitor/support-files/plugins/Telegraf/**/UI.json] -> 补 288 个插件 UI.json interval default_value 10 → 60。原 plan「采集频率默认 60s」漏了前端表单(只 grep 了 .py/.yaml/.go/.toml,完全没覆盖 .json)。新增 test_plugin_ui_default_interval.py 回归保护 + 一次性 Python 脚本批量改完 288 个文件,2 个 commit 已 push origin。本轮「采集频率 60s」三端覆盖完成:server 模型 default / K8s Telegraf ConfigMap / 前端 UI.json form default。 [server/apps/monitor/support-files/plugins/] (fixed)
- [OPEN] #0009 本地 master 已包含主机 Telegraf 节点名称默认实例名改动，但创建监控实例时选择节点后 instance_name 仍未自动填写 [monitor/integration/host-telegraf] (open)
- [OPEN] #0008 monitor 0045 migration also includes pre-existing algorithm verbose_name drift (commit d38cada17 changed verbose_name 聚合算法→周期聚合算法 without migration) [server/apps/monitor/migrations/0045_alter_monitorinstance_interval_and_more.py] (open)
- [OPEN] #0007 Sidecar 容器(融合采集器)持续 401/500,节点被标 inactive:get_client_token 在 token_auth.py:25 用 split(':', 1)[0] 取 Basic 头用户名,但容器发的 Basic 头是 "admin:" + token,抽到的不是 token 而是 "admin",导致后续 decode_token(urlsafe_b64decode("admin")) 失败抛 "token 解析失败" [server/apps/node_mgmt/utils/token_auth.py:25] (open)
  - Failed attempt: 误判:把 fusion-collector "节点不活跃" 归因到 server 端 token_auth.py:25 split 索引 bug,实际根因是 sidecar 进程内部状态卡住(长连接死/永久失败标记),用户 docker restart bklite-dev-fusion-collector 后立刻恢复,无需改 server 代码。教训:容器内 python 模拟 HTTP 请求不能证明 sidecar 进程自身行为,需要看进程级 socket/fd 或抓 sidecar 实际发出的请求才能下结论 [server/apps/node_mgmt/utils/token_auth.py:25]
- [OPEN] #0006 网络设备(华为 Telegraf 插件)实例识别失败:network device instance requires cloud_region and ip [server/apps/monitor/views] (open)
  - Failed attempt: 根因定位:前端 useDataMapper 在提交前对 instance_id 做了 FNV-1a + base64 哈希截断(16 字符),后端 network device identity adapter 无法从哈希串切出 cloud_region/ip,导致 "实例识别失败: network device instance requires cloud_region and ip" [web/src/app/monitor/hooks/integration/useDataMapper.ts:316-321]
- [DONE] #0005 vmware 插件分组规则编辑报错"监控实例与监控对象不匹配",子对象丢失 [web/src/app/monitor/(pages)/event/strategy/detail] -> vmware 父实例自动建子规则编辑失败:已在 _validate_rule_binding 中为 derivative 子对象放行父实例绑定(MonitorObject.parent_id == instance.monitor_object_id),保留 base 严格校验;新增 3 个测试覆盖 derivative-父实例合法、derivative-无关实例仍拒绝、PUT 端到端 200 [server/apps/monitor/views/organization_rule.py] (fixed)
- [DONE] #0004 P1-helper 模式类型过宽: getCalculationUnitOnMetricRowsChange 的 previousMode/nextMode 用 string,允许传非法模式字面量(如 'single'),调用方契约应是 MetricExpressionMode 字面量联合 [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] -> 收紧公式单位 helper 的 mode 类型为 MetricExpressionMode,修对测试 fixture;提交 590fa8ebb 已在 fix/monitor-formula-result-unit 分支上,Task 2 可基于收紧后的类型继续对称 retract 改造 [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] (fixed)
- [DONE] #0003 修复公式模式切换默认单位与枚举阈值误判：新增 helper 区分切换/编辑回填，并让公式模式阈值按非枚举处理 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] -> 最终 review 提出的公式默认单位与枚举阈值问题已通过 c8a1ddf2c 修复并验证 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] (fixed)
- [DONE] #0002 监控公式结果单位实现仍会在切换公式时继承单指标单位，并用第一指标枚举单位影响阈值输入 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] -> 公式模式切换现在默认 percent，公式阈值枚举判断不再依赖首个指标单位；聚焦测试、改动文件 lint、type-check 已通过 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] (fixed)
- [DONE] #0001 added formula result unit helpers and focused script entry for monitor strategy detail logic; focused test passed [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] -> formula result unit helpers and focused logic test now pass for monitor strategy detail [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] (fixed)

## Decisions
- 监控策略详情页的公式结果单位继续复用 calculationUnit 状态，由 strategyDetailUtils helper 统一做默认值和阈值单位过滤推导。 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx]
- 【监控系统】采集频率默认 60 秒,不用 10 秒:10 秒太短,对采集端/后端压力大、噪声多;60 秒是平衡实时性和成本的合理默认。新增监控采集相关默认值时遵循此规则。 [server/apps/monitor/]
- 主机（Telegraf）选择节点后，以节点真实 name 作为 instance_name 默认值；实例名称仍可编辑，重新选节点时刷新，清空或无法解析节点时不覆盖现值；通过声明式 change_handler 配置且仅对该插件启用。 [web/src/app/monitor/hooks/integration/]
- Task 2 决策:保留 Django 自动生成的 0045 migration,带 algorithm verbose_name drift 修复(避免下轮 makemigrations 重新生成) [server/apps/monitor/migrations/0045_alter_monitorinstance_interval_and_more.py]

## Notes
- gotcha: 在 `cd web && pnpm test:monitor-strategy-detail-logic` 场景下，pnpm 会触发工作区安装并打印 `prepare: .git can't be found` 警告；这是当前环境现象，不影响任务本身。 [web]
- gotcha: `cd web && pnpm lint && pnpm type-check` currently fails on pre-existing unrelated lint violations in Alarm/CMDB/Storybook files, so Task 3 verification cannot fully pass without broader cleanup. [web]
- worktree 内 web/ 没有 tsconfig.lint.json(它是仓库里的本地未追踪文件,不在 git 历史里,worktree 创建时不会自动带入),brief 里的 type-check 命令需要从主仓库复制一份才能跑;本 task 改用主 tsconfig.json(同样覆盖 strategy detail)验证 [web/tsconfig.lint.json]
- gotcha: server/.env 与 server/.env.local 容易脱节;dev 走 .env.local,manage.py 默认 load_dotenv() 只找 .env,跑 plugin_init / shell 会因密码错失败。统一做法:把 .env.local 追加到 .env 末尾(原内容用 # 注释保留做 fallback) [server/.env]
- gotcha: web/ 未跟踪 pnpm-lock.yaml，隔离 worktree 中 `pnpm install --frozen-lockfile` 会报 ERR_PNPM_NO_LOCKFILE；本地 worktree 初始化需用 `pnpm install --no-frozen-lockfile`，不要提交生成依赖产物。 [web/]
- gotcha: worktree 执行 `pnpm install --no-frozen-lockfile` 会在依赖安装完成后因 pnpm ignored-builds 返回非零，且 husky 报 `.git can't be found`；node_modules 仍可用于 tsx 聚焦测试，避免交互式 approve-builds 和提交新 lockfile。 [web/]
- gotcha: 2026-07-09 本地收口执行 `git pull --ff-only` 时 GitHub HTTPS 出现 LibreSSL SSL_connect SSL_ERROR_SYSCALL；本地合并可继续，但远端同步状态未验证。 [git/github]

## Key files
- `tsconfig.lint.json`
- `tsconfig.json`
- `rule.monitor`
- `instance.monitor`
- `MonitorObject.parent`
- `server/.env`
- `server/.env.local`
- `.env.local`
- `manage.py`
- `token_auth.py:25`
- `pnpm-lock.yaml`
- `MonitorInstance.interval`
- `UI.json`
- `.py/.yaml/.go/.toml`
- `test_plugin_ui_default_interval.py`

## Open questions
- None logged yet.
