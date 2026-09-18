# 告警筛选字段与多值匹配

日期：2026-09-10。状态：用户已确认，已实施并完成本地功能、完整性和链路验证；尚未部署。

2026-09-15 交互调整：五入口告警源改为可搜索下拉多选，显示名称和 ID，按名称保存；支持同名选项合并、旧名称回显和加载失败重试。本次不新增独立 ID 匹配字段。前端字段条件矩阵 353 项、页面与组件回归 241 项、候选接口权限测试 8 项通过；TypeScript 和定向 ESLint 检查通过。测试证据分别见 `/tmp/source-dropdown-tests.log`（矩阵通过部分）、`/tmp/source-dropdown-final-tests.log` 与 `/tmp/source-dropdown-api-tests.log`。

本轮进一步完成五入口每个字段 × 每个条件的独立交叉测试：后端入口、公共编辑器、正式表单均覆盖 **174/174** 组合。新增 1096 项后端测试，并修复首次运行时内置 CMDB Provider 未注册的问题；完整矩阵、最新回归数字及未覆盖边界见 [交叉测试报告](cross-product-test-results.md)。

完整字段矩阵与业务边界见 [实施文档](implementation-plan.md)，本轮证据见 [业务匹配测试报告](business-matching-test-results.md)。此前 [测试记录](test-results.md) 属于被取代的旧契约，不能作为本轮验收依据。

2026-09-15 字段与查询类型核对：五入口字段、操作符、中文文案和值控件与契约一致；新增界面目录测试，修改本功能时优先跑下面命令。

## 修改筛选时优先跑

改 `rule_fields.json`、操作符、匹配语义、`matchRule` 编辑器或五入口保存回显时，**先跑这组**，不要只改生产目录。先改 [独立契约](field-operator-test-matrix.json) 和目录测试里的中文期望，再改实现。

前端（目录测试最快暴露字段或查询类型错误）：

```bash
cd web
pnpm exec vitest run src/app/alarm/components/__tests__/ruleFieldOperatorCatalog.test.tsx src/app/alarm/components/__tests__/field-operator-cross-product.test.tsx
```

后端（须覆盖 addopts，避免复用旧测试库）：

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/alerts/tests/test_field_operator_cross_product_service.py apps/alerts/tests/test_multivalue_completeness_service.py --nomigrations -o addopts= --no-cov
```

完整交叉、正式表单和 alerts 全量见 [交叉测试报告](cross-product-test-results.md)。

## 当前契约

五个入口共用字段目录：相关性、屏蔽、丰富匹配 Event；分派、处理匹配 Alert。实际字段为单值，不妨碍条件输入多个候选值。

| 字段 | 条件 | 输入 |
| --- | --- | --- |
| 标题、正文/内容 | 等于、不等于、文本包含、文本不包含 | 单字符串 |
| 级别 | 包含、不包含（any_of/none_of） | 对应场景枚举下拉多选，保存代码数组 |
| Event 告警源 source_name | 包含、不包含（完整名称候选） | 下拉多选，可搜索名称、ID 和接入标识 |
| Alert 告警源 source_names | 包含任一、包含全部、不包含 | 下拉多选，可搜索名称、ID 和接入标识 |
| Event 监控源 push_source_id | 包含、不包含（完整值候选） | 回车标签 |
| Alert 监控源 push_source_ids | 包含任一、包含全部、不包含 | 回车标签 |
| 类型对象、对象实例 | 包含、不包含（完整值候选） | 回车标签 |
| 资源名称、指标；Event 服务、位置 | 属于任一、不属于任一、文本包含、文本不包含、正则 | 候选条件为标签，文本条件为单输入 |

Alert 告警源通过关联 Event.source.name 派生，排除 action=recovery，忽略空名称并按名称去重。closed 事件仍参与。包含全部允许额外来源，不包含要求有效集合非空。名称精确区分大小写；不同来源 ID 同名归为同一名称，改名后按最新名称匹配。

source_names 不新增数据库列；Alert.source_name 保留通知和参数绑定的原有快照用途。监控源 push_source_ids 仍为持久化 JSON 字符串数组，本次告警源排除恢复事件不改变监控源维护范围。

## 校验与交互

- 五个入口在“满足以下全部条件”旁提供“字段与匹配说明”浮层，按当前入口展示字段、操作符与输入方式；字段和操作符复用当前目录。说明区分文本、完整候选值和集合匹配，并解释 AND/OR、空值、标签输入限制及 Alert 告警源排除恢复事件的边界。
- 候选条件始终保存非空字符串数组，单候选也保存数组；不将数组包装为 eq 或字符串 contains。
- 告警源从现有来源下拉多选，支持搜索名称、ID 和接入标识；按名称去重保存，名称中的逗号不拆分，已保存但不在候选中的名称仍回显。ID 仅用于识别选项，匹配协议仍使用名称。
- 空实际值对所有条件均不命中，否定亦如此；非法字段、操作符或形状使整条规则不命中。API 拒绝非法保存。
- 新建未填写条件显示输入提示；不合法存量条件提示重新配置，不补入历史字段选项。
- 保留组内 AND、组间 OR；最多 20 组、100 条条件、每个候选数组 1–50 项、字符串最多 256 字符。

## 实现与生命周期

后端目录 rule_fields.json 生成前端字段目录，统一期望值类型、字段用途、操作符及取值路径。Event ORM 使用 source__name；入库前丰富使用已解析来源名称；Alert 来源解析器供 ORM、处理上下文、详情、列表及关联告警复用。

关联来源采用 Exists，不展开连接导致 Alert 重复；列表按批次读取，处理按一次评估按需读取并复用。列表新参数 source_names 接受 JSON 字符串数组，支持名称含逗号；旧 source_name 参数保持原协议。

沿用既有聚合、待分派重试、动作触发及幂等。追加非恢复事件影响之后的评估，不引入来源变化触发，不自动重分派或撤销动作；异步处理读取执行时的关联状态。

## 发布边界

告警源方案不新增来源模型列，此前监控源模型迁移仍是依赖。2026-09-14 补充一次性数据迁移 `0033_migrate_legacy_match_rules`，随正常 `migrate` 升级五入口旧规则，由 Django 迁移记录保证成功后不重复执行。2026-09-16 调整为：不能安全转换时记录策略类型、ID 和异常类型，保留整条策略并继续迁移其他策略；迁移正常完成并记录版本，跳过项需按新版目录人工重新配置，不会随 migrate 自动重试。数据库失败仍回滚并上抛。该方案替换独立 management 命令。历史模型、发布备份、不可逆边界及测试证据见 [存量规则迁移说明](legacy-migration.md)。前后端与全部规则 Worker 协调发布。

本地已通过后端 1802 项（另 1 项因 SQLite 不支持行锁跳过）、前端 60 项、类型及定向静态检查和五场景浏览器验证。尚未完成生产数据库执行计划、锁竞争及真实外部服务投递联调；详细范围和命令见测试报告。
