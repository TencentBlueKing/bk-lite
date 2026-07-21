# 监控接口性能优化设计

## 背景

监控页面存在两类明显慢请求：菜单与监控对象接口在冷启动阶段约 12 秒，多条 VictoriaMetrics `query_range` 请求约 1～3 秒。只读基准确认：

- `LanguageLoader` 首次加载监控中文翻译时会解析 289 个插件 YAML，约 2.58 MB，本地耗时 4.35～6.35 秒；热缓存后的 `monitor_object` 请求约 0.18 秒。
- `monitor_object` 在 47 个监控对象、3 个实例的本地数据集上执行 57 条 SQL，其中 46 条是读取 `MonitorObjectType` 的 N+1 查询。
- 开启断点检测且 `step` 等于 `collection_interval` 时，同一 PromQL、时间范围和步长会被串行查询两次。
- 实例数量统计会读取全部未删除实例及其组织关系，再逐条执行 Python 权限判断，成本随全局实例量增长。

## 目标

1. 保留 `LanguageLoader(app, lang)` 通用调用接口，同时消除普通应用误扫监控插件语言资源和监控请求冷启动解析大量 YAML 的问题。
2. 在不改变断点检测结果的前提下，消除相同步长的重复 VictoriaMetrics 查询。
3. 消除监控对象类型序列化的 N+1 SQL。
4. 在保持现有权限结果不变的前提下，缩小实例数量统计的数据库候选集。
5. 用行为测试和性能回归指标证明优化有效，不以缓存、权限或响应契约变化换取速度。

## 非目标

- 不调整监控页面一次展示哪些指标，也不改变前端懒加载和并发策略。
- 不合并不同 PromQL 为一个复杂查询。
- 不改变 `check_instance_permission` 的授权语义。
- 不引入 Redis、数据库翻译表或新的外部服务。
- 不处理本轮截图中的 Next.js 308 尾斜杠重定向和 HTTP 压缩；它们收益较小，可另行优化。

## 方案选择

### 方案 A：仅让 monitor 扫描插件 YAML

普通应用不再受影响，改动最小，但 monitor 首次加载仍需解析 289 个 YAML，无法解决核心冷启动问题。

### 方案 B：生成聚合 JSON，运行时兼容回退

部署初始化阶段将插件语言 YAML 合并为每种语言一个 JSON。`LanguageLoader` 保持通用入口，monitor 优先读取聚合文件；文件不可用时回退现有扫描逻辑。该方案兼顾性能、兼容性和故障可恢复性。

### 方案 C：翻译进入数据库或 Redis

可以跨进程共享，但会引入部署依赖、缓存失效和数据迁移问题，超出本次性能优化需要。

采用方案 B。

## 设计

### 1. 通用语言加载与插件聚合资源

`LanguageLoader` 继续负责三类来源的合并：应用基础翻译、应用专属扩展翻译、企业覆盖。普通应用只加载自己的基础与企业目录；只有 `app == "monitor"` 时才加载监控插件翻译。

新增插件语言聚合器，复用现有插件发现顺序和深度合并规则：

1. 按 `PluginConstants.DIRECTORY`、`PluginConstants.ENTERPRISE_DIRECTORY` 顺序扫描插件。
2. 读取 `metrics.json` 的 `plugin` 名称和同目录 `language/{lang}.yaml`。
3. 保持当前 `monitor_object_plugin` 包装及共享翻译段的合并方式，企业插件继续覆盖内置插件。
4. 以 UTF-8 JSON 写入每种支持语言的聚合文件。
5. 先写同目录临时文件，写入和 `fsync` 成功后使用 `os.replace()` 原子替换，避免 worker 读到半文件。

聚合目录由 `PLUGIN_LANGUAGE_CACHE_DIR` 配置；默认使用 `settings.BASE_DIR/.runtime/plugin-languages/`，并将 `.runtime/` 加入 `server/.gitignore`。文件名固定为 `plugins-en.json` 和 `plugins-zh-Hans.json`，因此 `batch_init`、本地开发服务和同一容器内的全部 Uvicorn workers 使用同一份资源。测试通过临时目录覆盖该配置，不接触真实运行目录。

聚合命令在部署的 `batch_init` 阶段运行。现有内存“预热”不能跨越管理命令和 Uvicorn worker 进程，因此改为生成可被后续 worker 共享读取的聚合文件。运行时行为如下：

- 聚合文件存在且可解析：直接加载 JSON。
- 聚合文件缺失、损坏或版本不兼容：记录明确 warning，回退现有 YAML 扫描，接口保持可用。
- 回退扫描成功后不在请求路径写文件，避免并发请求争抢；聚合文件只由部署初始化命令生成。
- 应用级内存缓存键仍为 `(app, lang)`，调用方无需改变。

聚合文件包含格式版本和来源顺序元数据，正文保存合并后的翻译对象。生成命令输出每种语言的插件数、文件数和结果大小；任一语言生成失败时 `batch_init` 失败，避免部署静默携带陈旧资源。运行时回退仅处理文件丢失或损坏等异常场景。

### 2. VictoriaMetrics 相同步长结果复用

`Metrics.get_metrics_range` 仍先执行展示数据查询。开启断点检测后：

- 若 `parse_step_to_seconds(step) == collection_interval`，直接使用首次响应中的原始 `result` 计算断点。
- 若两者不同，继续以采集间隔发起第二次精细查询。
- 断点检测必须发生在 `fill_missing_points` 之前，确保只分析 VictoriaMetrics 返回的真实点，而不是服务端补点。
- 查询失败、点数上限和非法采集间隔的现有处理保持不变。

该优化在截图中的 10 秒步长场景以及默认短时间窗口中，可将每个图表的上游查询从两次降为一次。

### 3. 监控对象类型关联预取

`MonitorObjectViewSet` 的基础 QuerySet 增加 `select_related("type")`。序列化器继续通过 `type_info` 输出相同字段，模型默认排序 `type__order、order、id`、过滤条件、分页和国际化逻辑均不改变。

测试不只断言总查询数，还必须确认对象数量增加时 `MonitorObjectType` 查询数不随对象数量线性增长。

### 4. 权限安全的实例数量候选集

继续使用 `check_instance_permission` 作为最终授权判断。优化仅在它之前构造不会漏掉合法实例的安全候选集。

候选组织 ID 是以下集合的并集：

- `cur_team`；
- `permissions["all"]["team"]`；
- 每个对象权限条目中的 `team`。

候选显式实例 ID 是所有对象权限条目 `instance[].id` 的并集。数据库候选条件为：

```text
is_deleted = false
AND (
  organizations.organization IN candidate_team_ids
  OR id IN candidate_instance_ids
)
```

查询使用 Django ORM、`distinct()` 和定向字段/关系预取，不使用原生 SQL。得到候选实例后，仍把真实组织集合、对象 ID、实例 ID、完整权限数据和 `cur_team` 传给 `check_instance_permission`；只有最终判断通过才计入对应监控对象。

若候选组织和显式实例集合都为空，QuerySet 直接使用 `.none()`，禁止空 `Q()` 退化为全表扫描。

这一设计保持以下场景不变：

- 超级管理员仅在当前授权组织范围内计数；
- 对象没有专属规则时按 `cur_team` 判断；
- 对象团队规则授权；
- 显式实例授权，即使实例不属于普通团队候选也不会被漏掉；
- 无组织且无显式授权的实例继续不可见；
- 非规范或空权限结果继续 fail-closed。

## 错误处理与可观测性

- 聚合命令失败必须返回非零退出码，并输出语言和源文件位置。
- 运行时聚合文件回退记录一次 warning，包含路径和异常类型，不记录翻译正文。
- VictoriaMetrics 调用异常继续沿用现有超时和请求异常处理。
- 权限候选集解析遇到未知结构时不扩大范围；无法识别的 ID 被忽略，最终仍由现有权限函数决定。
- 现有 `RequestTimingMiddleware` 继续记录慢接口；性能验收同时记录冷、热耗时和 SQL/上游调用数。

## 测试策略

所有生产代码按 TDD 实现，先观察回归测试在旧实现上失败。

### 语言加载

- 聚合结果与旧 YAML 扫描结果完全相同。
- 内置与企业插件覆盖顺序保持一致。
- 普通 app 不调用插件加载路径。
- monitor 优先读取聚合 JSON。
- 聚合文件缺失、损坏时回退 YAML。
- 原子写入失败不覆盖上一份有效文件。
- `batch_init` 生成两种支持语言的文件并传播失败。

### VictoriaMetrics

- `step` 与采集间隔相同时 `query_range` 只调用一次，断点结果正确。
- 步长不同时仍调用两次，第二次使用采集间隔。
- 点数超限、关闭断点检测和非法间隔行为不变。

### ORM 与权限

- 多个对象共享或使用不同类型时不出现类型 N+1。
- 管理员团队、默认当前团队、对象团队、显式实例、拒绝路径分别覆盖。
- 优化后的实例计数与逐条全量基准算法对同一 fixture 结果一致。
- 候选 ORM 不读取权限范围外的大量实例。

## 验收标准

1. 普通应用首次 `LanguageLoader` 不访问监控插件目录。
2. monitor 使用聚合资源时不解析插件 YAML；本地冷加载目标小于 500 ms，且较当前基准至少降低 80%。
3. 47 个对象 fixture 下，对象列表 SQL 数不再随对象数量增加；类型关联只随主查询一次读取。
4. 相同步长断点检测的 VictoriaMetrics 调用数由 2 降为 1，响应数据与优化前一致。
5. 实例统计在全部权限 fixture 上与旧算法结果一致，并且数据库候选不包含无关组织且未被显式授权的实例。
6. 相关专项测试、Server 模块回归、格式/静态检查和迁移检查全部通过。

## 发布与回滚

部署顺序不变：迁移与 `batch_init` 完成后启动 Uvicorn。新 `batch_init` 会先生成聚合资源；worker 读取失败时自动回退旧扫描路径，因此聚合资源异常不会直接造成接口不可用。

回滚代码后，旧 `LanguageLoader` 会忽略聚合 JSON 并继续扫描 YAML。聚合文件不包含业务数据和凭据，可随容器生命周期清理。
