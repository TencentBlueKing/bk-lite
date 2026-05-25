## Context

`AlgorithmConfig` 已经作为 MLOPS 六类算法共用的配置表存在，并且当前模型层已经提供了 `algorithm_type` 枚举、`(algorithm_type, name)` 唯一约束，以及 `form_config` 的 JSON 存储能力。但现阶段没有任何自动初始化链路，导致部署后只能依赖手工创建配置，或在部分运行路径中退回到 `DEFAULT_IMAGES` 这样的局部兜底逻辑。

这次变更的目标不是引入一套完整的配置同步系统，而是补一个“首装默认值导入”能力。设计上需要同时满足几个约束：

- 默认算法配置内容较长，尤其 `form_config` 可能是大体量 JSON，不适合写进 Python 常量或 migration。
- 初始化不能覆盖数据库里已有的用户配置。
- 初始化命令接入 `batch_init` 后，不能因为单个坏文件而阻塞全局启动链路。
- 当前不引入 `dataset_requirement_rules` 等尚未实现的字段，默认文件格式必须与现有模型和前端消费能力严格对齐。

## Goals / Non-Goals

**Goals:**

- 为 MLOPS 增加一个从仓库默认文件初始化 `AlgorithmConfig` 的 bootstrap 入口。
- 将默认算法配置从代码中分离到 `support-files/algorithm-configs/`，便于维护、评审和扩展。
- 将初始化行为定义为首次幂等写库：不存在创建，已存在跳过。
- 将初始化命令纳入 `batch_init` 可调用范围，并使用非阻塞方式融入全局初始化流程。
- 为初始化过程提供清晰的命令输出和必要的 `mlops_logger` 生命周期日志记录。

**Non-Goals:**

- 不实现默认配置和数据库记录之间的双向同步或增量更新。
- 不在本次设计中引入 `dataset_requirement_rules` 或其它未来字段。
- 不深度校验 `form_config` 内部 schema，只校验其顶层类型为 JSON object。
- 不允许通过 support-files 直接扩展新的 `algorithm_type`；新增类型仍需先修改模型与系统分支逻辑。

## Decisions

### 1. 默认配置存放在 `server/apps/mlops/support-files/algorithm-configs/`

选择 support-files 的原因是它与仓库中“内置默认配置”的现有组织方式一致，也适合承载长 JSON 结构。相比把 `form_config` 放进 Python 常量：

- JSON 文件更接近最终数据结构，减少序列化和转义负担。
- review 和 diff 更直观，便于按算法单独维护。
- 避免让某个 Python 模块变成大段静态配置堆积点。

选择一算法一文件，而不是拆成多个碎文件，是为了保持最小设计。当前一条算法配置天然就是一个整体对象，没有必要现在引入多文件拼装。

### 2. 目录结构固定为 `<algorithm_type>/<name>.json`

初始化命令只扫描白名单 `algorithm_type` 目录下的直接 `.json` 文件。这样做的原因是：

- `algorithm_type` 已经是模型层受控字段，目录名应该与现有枚举保持一致。
- `name.json` 与 JSON 内部 `name` 一致，可以减少双写漂移，方便定位和排障。
- 不递归扫描可以保持实现简单，也避免未来 support-files 中夹杂其它辅助文件时被误处理。

替代方案是把 `algorithm_type` 也写进 JSON，但这会形成目录和文件内容的双重来源，不一致时反而更难处理，因此不采用。

支持的目录白名单应当在运行时从 `AlgorithmConfig.ALGORITHM_TYPE_CHOICES` 派生，而不是在命令中再维护一份硬编码列表。这样可以保证默认文件导入逻辑与模型层约束保持一致。

### 3. JSON 顶层字段采用最小契约

当前文件仅允许以下字段：`name`、`display_name`、`image`、`scenario_description`、`form_config`。

这样设计的原因是：

- 这几项与现有 `AlgorithmConfig` 字段直接对应，能无歧义写入。
- `dataset_requirement_rules` 还未实现，不应提前进入默认文件格式。
- 将未知字段视为非法，可以避免 support-files 先演进、后端能力未接上的半成品状态。

对 `form_config` 只做“必须是 object”的弱校验，是为了把初始化职责限定为导入默认值，而不是承担前端 schema 编译器的职责。

默认文件契约虽然比数据库模型更严格，但这是有意设计：例如 `scenario_description` 在模型层允许为空，而默认内置配置仍然要求必须提供该字段，以保证内置算法配置具备完整的展示说明。

JSON 契约之外的字段不参与导入：`is_active` 使用模型默认值 `True`，其余维护信息字段使用系统创建时的默认写入方式，不要求默认文件显式提供。

### 4. 初始化命令采用首次幂等写库，不做更新

写库行为按现有唯一键 `(algorithm_type, name)` 判断：

- 不存在：创建
- 已存在：跳过

不做更新、不补字段、不覆盖的原因是当前更重要的是保护已有用户配置。算法镜像、显示名、场景描述和表单配置都有可能在部署后被人工调整，如果初始化命令带覆盖能力，会把 bootstrap 变成同步器，风险明显提高。

替代方案是“创建或更新内置配置”，但这需要额外区分哪些记录是系统内置、哪些记录是用户维护，这超出了本次范围，因此不采用。

并发执行时，首次写库判断也必须保持原子性。若采用“先查询是否存在，再执行创建”的两步式实现，在多实例同时启动或并发执行初始化命令时，可能在 `(algorithm_type, name)` 唯一键上产生竞争，导致唯一约束冲突并中断当前导入流程。

因此，实现层应采用原子 first-write 方案（如 `get_or_create()` 或等价数据库原子操作），保证并发情况下仍满足以下语义：

- 最多创建一条对应 `(algorithm_type, name)` 的记录。
- 已存在的记录视为 `skipped_existing`。
- 单条记录的并发竞争不应中断同一轮导入中后续文件的处理。

### 5. 坏文件不阻塞整体导入，也不阻塞 `batch_init`

初始化命令对目标 JSON 文件做逐个处理。单个文件解析失败、字段非法、`name` 与文件名不一致时，记为 `skipped_invalid` 并继续处理其它文件。

这样设计的原因是：

- 该命令是默认值导入，不是系统核心 schema 初始化。
- 仓库现有 `batch_init` 已经对非关键模块采用“记录错误后继续”的模式。
- 单个默认算法配置损坏不应该拖垮整个服务启动。

同时，命令必须打印清晰的 `created / skipped_existing / skipped_invalid` 汇总，并在命令输出中给出每个坏文件的失败原因，避免问题被静默吞掉。

### 6. 输出统一复用 management command 输出，并保留 `mlops_logger` 生命周期日志

仓库中已经存在 `apps.core.logger.mlops_logger`，且 MLOPS 服务和任务代码已在复用该 logger。因此新命令不引入新的日志入口，而是沿用：

- `self.stdout.write(...)` / `self.stderr.write(...)` 用于初始化过程、坏文件原因和部署控制台输出
- `mlops_logger` 用于命令开始、创建、跳过和最终 summary 等模块生命周期日志

这样可以保持与现有初始化命令和 MLOPS 模块风格一致。

## Risks / Trade-offs

- **[默认文件变更不会自动同步到旧环境数据库]** → 这是首次幂等写库的直接代价。通过明确将命令定位为 bootstrap，而不是同步器来降低歧义；后续若需要更新能力，再单独设计。
- **[弱校验可能让结构上可写库但前端不可用的 `form_config` 进入数据库]** → 当前只把初始化命令定位为默认数据导入，避免过早引入复杂 schema 校验；后续可通过算法配置管理界面或单独校验逻辑补强。
- **[support-files 内容增多后维护成本提升]** → 通过固定目录结构、一算法一文件和文件名一致性约束，保持配置可维护性。
- **[单个文件错误不会阻断全局初始化，可能导致部分默认算法缺失]** → 通过 summary 和错误日志让问题在部署日志中可见，避免完全静默失败。
- **[多实例并发初始化可能在同一默认算法记录上发生竞争]** → 实现必须使用原子 first-write，避免因唯一约束冲突中断整轮导入。

## Migration Plan

1. 在 `server/apps/mlops/support-files/algorithm-configs/` 下建立六类 `algorithm_type` 目录结构，并先选取一类算法配置作为首批验证样本。
2. 新增 `init_algorithm_config` management command，实现扫描、校验、首次幂等写库和日志输出。
3. 在 `batch_init.py` 中增加 `_init_mlops()`，并通过 `call_command("init_algorithm_config")` 暴露 MLOPS 初始化入口。
4. 将 `mlops` 纳入 `batch_init` 默认 app 列表，使默认初始化链路自动执行算法配置 bootstrap。
5. 使用首批验证样本完成初始化验证，确认命令行为、日志输出和幂等写库符合预期。
6. 验证通过后，再逐步补充其余算法 JSON 文件，扩展到六类算法的实际默认配置。

回滚策略：

- 若命令实现存在问题，可先从 `batch_init` 中移除 `mlops` 调用，恢复到原有手工配置模式。
- 若已写入错误默认配置，可按 `(algorithm_type, name)` 手工删除对应记录；由于本次命令不做覆盖，不会影响已有用户记录的字段更新逻辑。

## Open Questions

None.
