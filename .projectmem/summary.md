# projectmem - bk-lite

_Last updated: 2026-07-08_

## Project purpose
BK-Lite is an AI-first lightweight operations platform for operations administrators. It combines a Django business backend, Next.js control consoles, mobile/desktop shells, distributed collection agents, and algorithm services to provide CMDB, monitoring, alerting, log, job, node, MLOps, and OpsPilot capabilities with low deployment cost and progressive operational workflows.

## Recent issues
- [OPEN] #0006 网络设备(华为 Telegraf 插件)实例识别失败:network device instance requires cloud_region and ip [server/apps/monitor/views] (open)
  - Failed attempt: 根因定位:前端 useDataMapper 在提交前对 instance_id 做了 FNV-1a + base64 哈希截断(16 字符),后端 network device identity adapter 无法从哈希串切出 cloud_region/ip,导致 "实例识别失败: network device instance requires cloud_region and ip" [web/src/app/monitor/hooks/integration/useDataMapper.ts:316-321]
- [DONE] #0005 vmware 插件分组规则编辑报错"监控实例与监控对象不匹配",子对象丢失 [web/src/app/monitor/(pages)/event/strategy/detail] -> vmware 父实例自动建子规则编辑失败:已在 _validate_rule_binding 中为 derivative 子对象放行父实例绑定(MonitorObject.parent_id == instance.monitor_object_id),保留 base 严格校验;新增 3 个测试覆盖 derivative-父实例合法、derivative-无关实例仍拒绝、PUT 端到端 200 [server/apps/monitor/views/organization_rule.py] (fixed)
- [DONE] #0004 P1-helper 模式类型过宽: getCalculationUnitOnMetricRowsChange 的 previousMode/nextMode 用 string,允许传非法模式字面量(如 'single'),调用方契约应是 MetricExpressionMode 字面量联合 [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] -> 收紧公式单位 helper 的 mode 类型为 MetricExpressionMode,修对测试 fixture;提交 590fa8ebb 已在 fix/monitor-formula-result-unit 分支上,Task 2 可基于收紧后的类型继续对称 retract 改造 [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] (fixed)
- [DONE] #0003 修复公式模式切换默认单位与枚举阈值误判：新增 helper 区分切换/编辑回填，并让公式模式阈值按非枚举处理 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] -> 最终 review 提出的公式默认单位与枚举阈值问题已通过 c8a1ddf2c 修复并验证 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] (fixed)
- [DONE] #0002 监控公式结果单位实现仍会在切换公式时继承单指标单位，并用第一指标枚举单位影响阈值输入 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] -> 公式模式切换现在默认 percent，公式阈值枚举判断不再依赖首个指标单位；聚焦测试、改动文件 lint、type-check 已通过 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] (fixed)
- [DONE] #0001 added formula result unit helpers and focused script entry for monitor strategy detail logic; focused test passed [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] -> formula result unit helpers and focused logic test now pass for monitor strategy detail [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] (fixed)

## Decisions
- 监控策略详情页的公式结果单位继续复用 calculationUnit 状态，由 strategyDetailUtils helper 统一做默认值和阈值单位过滤推导。 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx]

## Notes
- gotcha: 在 `cd web && pnpm test:monitor-strategy-detail-logic` 场景下，pnpm 会触发工作区安装并打印 `prepare: .git can't be found` 警告；这是当前环境现象，不影响任务本身。 [web]
- gotcha: `cd web && pnpm lint && pnpm type-check` currently fails on pre-existing unrelated lint violations in Alarm/CMDB/Storybook files, so Task 3 verification cannot fully pass without broader cleanup. [web]
- worktree 内 web/ 没有 tsconfig.lint.json(它是仓库里的本地未追踪文件,不在 git 历史里,worktree 创建时不会自动带入),brief 里的 type-check 命令需要从主仓库复制一份才能跑;本 task 改用主 tsconfig.json(同样覆盖 strategy detail)验证 [web/tsconfig.lint.json]

## Key files
- `tsconfig.lint.json`
- `tsconfig.json`
- `rule.monitor`
- `instance.monitor`
- `MonitorObject.parent`

## Open questions
- None logged yet.
