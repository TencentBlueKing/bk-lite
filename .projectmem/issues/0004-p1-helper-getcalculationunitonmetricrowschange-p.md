# #0004 P1-helper 模式类型过宽: getCalculationUnitOnMetricRowsChange 的 previousMode/nextMode 用 string,允许传非法模式字面量(如 'single'),调用方契约应是 MetricExpressionMode 字面量联合

- 2026-07-08T08:41:02Z `issue`: P1-helper 模式类型过宽: getCalculationUnitOnMetricRowsChange 的 previousMode/nextMode 用 string,允许传非法模式字面量(如 'single'),调用方契约应是 MetricExpressionMode 字面量联合 [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts]
- 2026-07-08T08:41:05Z `attempt`: 把 previousMode/nextMode 改为 MetricExpressionMode,同步把测试 fixture 的 'single' 改为 'metric',新增 'formula'→'metric' 反向 assert;测试 + lint + type-check(strategy detail)均通过,提交 590fa8ebb [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts] (worked)
- 2026-07-08T08:41:07Z `fix`: 收紧公式单位 helper 的 mode 类型为 MetricExpressionMode,修对测试 fixture;提交 590fa8ebb 已在 fix/monitor-formula-result-unit 分支上,Task 2 可基于收紧后的类型继续对称 retract 改造 [web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts]
