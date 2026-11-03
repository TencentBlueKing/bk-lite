# OpsPilot 内置 MLOps 时序预测工具与 MLOps NATS predict 接口

Status: proposed

## Problem Statement

用户在 OpsPilot 对话里问「未来 7 天哪台服务器磁盘可能爆满」「这台机器内存接下来一个月的走势」时，目前只能让大模型直接对监控数据心算外推，结果有幻觉、不可复现。MLOps 已有训练好的时序预测能力（`TimeSeriesPredictServing` + `TimeSeriesPredictServingViewSet.predict`，`server/apps/mlops/views/timeseries_predict.py` L1712），但：

- MLOps 的 NATS 接口（`server/apps/mlops/nats_api.py`）只有模块清单与分页列表（`get_mlops_module_list` / `get_mlops_module_data`），没有预测调用；
- OpsPilot 没有对应的内置工具，模型无法把监控序列交给已训练的预测服务；
- 预测服务对输入有硬约束（Unix 秒时间戳、时间戳必须规则否则报「无法推断时间频率」、`steps` 是未来点数而非天数），监控原始数据（毫秒时间戳、5 分钟粒度、带缺口、按维度拆成多条序列）不能直接喂入。

## Solution

1. MLOps 侧新增一个 NATS 方法 `predict_timeseries_serving`，只转调现有 `predict` 的业务逻辑（参数校验、`build_predict_url`、HTTP 调用预测容器、错误映射），不改任何预测行为。
2. OpsPilot 侧新增内置工具 `mlops`（挂一个方法 `mlops_predict_timeseries`），负责：绑定 serving、从本轮监控工具结果或用户贴出的序列取数、按预测跨度定频率和步长、下采样整形、并发调用 NATS、把结果裁剪成「摘要 + 趋势」两层给模型。
3. 智能体配置时从当前组织已发布的 `TimeSeriesPredictServing` 中选择服务（经现有 `get_mlops_module_data(serving, timeseries_predict_serving)` 列表）；运行时权限仍由 MLOps 按当前对话用户校验。

数据流：模型调监控工具拿原始序列 → 模型调 `mlops_predict_timeseries`（传 metric 引用或用户贴的 data）→ 工具整形后逐序列调 NATS → MLOps 转调 predict → 工具汇总摘要/趋势返回模型 → 模型组织回答。MLOps 不连接监控，不自己取数。

## User Stories

1. As a 运维人员, I want 问「未来 7 天哪台主机磁盘可能爆满」时得到基于已训练模型的预测排序, so that 不被大模型心算的幻觉数字误导。
2. As a 运维人员, I want 问某台机器某指标的未来走势时得到合理密度的预测点（7 天约 168 点、30 天约 360 点）, so that 既看得出趋势又不被数千个原始粒度点淹没。
3. As a 运维人员, I want 直接把一段时序数据贴进对话让智能体预测, so that 不依赖监控接入也能用预测能力。
4. As a 智能体管理员, I want 在智能体配置里明确选定用哪个（将来哪些）已发布预测服务, so that 模型不能自己换一个未经认可的服务。
5. As a 平台管理员, I want 对话用户必须自己具备 `timeseries_predict-Predict` 权限和服务所在组织, so that 配置了工具的智能体不会成为越权通道。

## Implementation Decisions

### MLOps NATS 接口

- `server/apps/mlops/nats_api.py` 新增：

  ```
  predict_timeseries_serving(serving_id, data, steps, actor_context, locale=None)
  ```

- `data` 为秒级 `[{timestamp, value}]`，`steps` 为未来点数；返回 `{result: bool, data | message}`，`data` 为现有 predict 响应（含 `history` / `prediction` / `metadata`，剥离 `history` 在 OpsPilot 侧做）。
- 实现只做身份/组织校验 + 转调现有 predict 业务逻辑；复用 `_validate_actor_group` 风格的 actor_context 校验，并校验调用用户具备 `timeseries_predict-Predict` 权限、serving 在其组织范围（与 `TeamModelViewSet` 的组织过滤同口径）。
- 不新增批量接口：一次 NATS 调用一条序列。
- 单次预测超时沿用现有 `get_timeseries_predict_timeout_seconds()`（默认约 125s），不另改。

### OpsPilot 内置工具注册

- 按现有内置工具模式（`services/builtin_tools.py`）新增 `BUILTIN_MLOPS_TOOL_ID = -11`、`BUILTIN_MLOPS_TOOL_NAME = "mlops"`，工具模块放 `metis/llm/tools/mlops/`。
- 与 monitor 等 identity-only 工具不同：绑定需要携带 `serving_ids` 配置（kwargs），前端配置界面通过 `get_mlops_module_data("serving", "timeseries_predict_serving", ...)` 列出当前组织可选服务供选择。
- 绑定存成 `serving_ids` 列表（现阶段界面只允许选 1 个，存储即为列表，为多选预留）：
  - 列表只有 1 个：运行时忽略模型传入的 `serving_id`，固定用这一个；
  - 将来多于 1 个：模型必须传列表内的 `serving_id`，传列表外的 ID 工具拒绝并在错误中带回可选服务的 id 和名称；
  - 工具描述始终写明已绑定服务的 id 和名称。
- 语言文件（`language/en.yaml` / `zh-Hans.yaml`）补 `tools.mlops.*` 描述。

### 工具签名

```
mlops_predict_timeseries(
  view,                  # "summary" | "trend"
  horizon_days,          # 用户要看的未来时长（天）
  serving_id=None,       # 始终存在；单绑定时被忽略
  metric=None,           # 引用本轮监控查询结果的指标名
  instance_ids=None,     # 可选，收窄实例
  data=None,             # 用户贴出的单条序列 [{timestamp, value}]
  threshold=None         # 用户明确说出的阈值；不默认 100
)
```

### 数据来源（互斥）

- `metric`：匹配本轮内最近一次成功的 `monitor_query_metric_data` 调用，且该次调用的 `metric` 参数与之相同；序列取其原始返回，不接受模型复述的点。传了 `instance_ids` 则只保留这些实例的序列。
- `data`：用户在对话中贴出的单条序列，原样接收。
- `metric` 与 `data` 同时传或都不传：拒绝，错误说明二选一。
- `metric` 对不上任何本轮监控结果：拒绝，让模型先调监控。
- 模型点名的 `instance_ids` 部分不在监控结果中：找到的照常预测，缺的每个 `instance_id` 记一条错误；一个都找不到则整批拒绝。

### 序列粒度

- 监控结果里的每条序列单独预测（同一主机的多个挂载点/维度是多条序列），结果标识带该序列完整标签（实例 + dimensions），不按主机合并，工具不自行挑「最高的盘」代表整机；用户问整机时由模型先用监控 `dimensions` 收窄。
- 单次调用序列数上限 100 条（按序列计，不按主机计）；超过整批拒绝，提示模型先用监控筛选（高用量/已告警实例）再预测。

### 整形（调 NATS 之前，全部在 OpsPilot 工具内完成）

- 时间戳统一成 Unix 秒：大于 10^12 的整数视为毫秒除以 1000（监控返回毫秒、预测服务只认秒）。
- 频率与步数由 `horizon_days` 决定，桶内取最后一个值下采样：

  | 跨度 | 频率 | steps |
  |---|---|---|
  | ≤ 2 天 | 15 分钟 | horizon_days × 96 |
  | ≤ 7 天 | 1 小时 | horizon_days × 24（7 天 = 168） |
  | ≤ 31 天 | 2 小时 | horizon_days × 12（30 天 = 360） |
  | 更长 | 继续拉长间隔 | steps ≤ 500 |

- 空桶不补值（不填 0、不前值填充）：桶内有任意点则取最后一个；整个桶无点则从最近一段连续桶向前取历史，更早的缺口丢弃。
- 历史窗口：下采样后最多送最近 `4 × steps` 个点；最近连续段少于 `2 × steps` 时该序列失败，错误写明至少需要的监控窗口长度与缺口位置。工具不自行加长监控查询。
- `steps` 含义即未来点数；工具描述写明「跨度 ÷ 输入点间隔」，服务端不做天数换算。频率推断失败等预测服务错误按该序列失败原样带回，模型不自行补点。

### 执行与超时

- 工具内部按序列并发调用 NATS，并发度 5。
- 工具内部整批墙钟 240 秒（低于外层 `TOOL_INVOKE_TIMEOUT` 默认 300 秒，保证已完成结果不被外层掐掉）：到点返回已完成序列，未完成的记为超时错误。
- 单序列失败（权限、频率推断失败、容器不可达、超时）只记在该序列的 `error`，不影响其余；至少一条成功则整批成功，全部失败则整批失败且各条原因保留在 `results` 中。

### 权限

- NATS 调用携带当前对话用户（复用 `caller_identity` 快照口径构造 `actor_context`），MLOps 按该用户校验 `timeseries_predict-Predict` 与组织范围；OpsPilot 的 `serving_ids` 绑定只是允许名单，不替代 MLOps 校验。
- 无 caller_identity 的触发方式（与监控工具同口径）返回明确错误。
- 权限拒绝原因原样交回模型。

### 返回给模型

- 不含 `history`，不含下采样前原始点。多序列按 `max_value` 降序。

  ```
  {
    serving: { id, name },
    frequency,            # "15m" | "1h" | "2h" | ...
    steps,
    view,
    results: [
      {
        instance_id,       # 序列标识（实例 + dimensions 标签）；用户贴的序列为空
        summary: {
          max_value, max_time, max_offset,
          final_value, final_time, final_offset
        },
        over_threshold,    # 仅传入 threshold 时存在：max_value >= threshold
        trend,             # 仅 view=trend：[{ timestamp, time, value }]
        error              # 该序列失败原因
      }
    ]
  }
  ```

- `view=summary`：只回每条序列摘要（多台比较场景）。
- `view=trend`：只允许 1 条序列，多条直接拒绝让模型先收窄；同时带回摘要与按频率下采样后的预测点。
- `timestamp` 为秒，`time` 为可读时间（调用方时区，缺省东八区），`offset` 为距最后一个历史点的时长。
- 传入 `threshold` 时才有 `over_threshold`，不默认阈值 100，也不过滤未超过的行。
- 工具描述指导模型：摘要层回答「哪台最危险、峰值何时出现」，趋势层才列点；预测跨度用频率 × 步数换算成真实时间表述。

## Testing Decisions

- MLOps NATS：`predict_timeseries_serving` 成功转调（mock HTTP）、actor_context 缺失/组织越权/无权限拒绝、serving 不存在、预测服务业务失败（success=false）与上游非 200 的错误透传；双组织隔离用例。
- 整形纯函数：毫秒→秒归一（边界 10^12）、各跨度频率/步数映射、桶内取最后值、空桶截断取最近连续段、`4×steps` 窗口与 `2×steps` 下限拒绝、缺口位置写入错误。
- 工具行为：`metric`/`data` 互斥与都缺拒绝；`metric` 匹配本轮最近一次同指标成功监控结果（多次查询取最近）；`instance_ids` 部分命中（命中照常、缺失记错）与全不命中整批拒绝；序列数 >100 拒绝；`view=trend` 多序列拒绝；单绑定忽略模型 `serving_id`、多绑定校验列表外拒绝并回带可选项。
- 并发与超时：并发度 5、240s 墙钟到点返回已完成 + 未完成记超时、单序列失败不污染其余、全失败整批失败。
- 返回裁剪：无 `history`、`max_value` 降序、`threshold` 缺省无 `over_threshold`、trend 仅在 view=trend 出现、时区回退东八区。
- 权限：caller_identity 缺失错误、MLOps 拒绝原因透传。
- 注册：内置工具出现在工具列表、`serving_ids` kwargs 结构、语言文件键存在（中英）。
- 日志按 `backend-engineering.md` §8：批量预测一条 INFO 终态汇总（序列数/成功/失败/耗时），单序列失败 DEBUG，错误含 `failed_stage` 与 `error_type`，不落序列数据。

## Out of Scope

- 预测结果的图表卡片/前端可视化（本期纯文本回答）。
- MLOps 批量预测接口、预测服务本身的行为与超时修改。
- 工具自动加长/重发监控查询；MLOps 自行连接监控取数。
- 绑定多 serving 的前端多选界面（存储结构已预留列表）。
- 异常检测、日志聚类等其他 MLOps 能力的工具化。
- 缺口插值/补点策略。

## Further Notes

- Grill 共识记录（2026-10-20）：
  - 调用对象是已发布的 `TimeSeriesPredictServing`，「技能 ID」即 serving ID；绑定时选定，现阶段单选，存储列表为多选预留，多选时由模型在绑定列表内选择、列表外拒绝。
  - NATS 只转调现有 predict，不改业务逻辑；一次一条序列。
  - 数据由模型侧提供：监控工具结果引用（`metric` + 本轮最近一次成功查询）或用户贴的 `data`，二者互斥；MLOps 不自己找数据源。
  - `steps` 是点数不是天数；频率表（15m/1h/2h）与 steps≤500 由用户确认；摘要项（最大值/最终值/出现时间）面向「哪台会爆满」场景，趋势层面向单台走势场景，`view` 参数保留由模型选择。
  - 50 台主机 = 1 次工具调用、内部 50 次 NATS（并发 5），不要求模型分 3 次抄数据。
  - 空桶不补值但单个原始缺点不致失败（桶内任一点即可）；取最近连续段，下限 `2×steps`。
  - 内部墙钟 240s < 外层 `TOOL_INVOKE_TIMEOUT` 300s。
  - 按序列（实例+维度）预测不按主机合并；`instance_ids` 部分命中不整批失败。
  - 阈值只认用户明说的，不默认 100。
- 关键事实依据：predict 文档中的 `url` 参数实现未读取，地址来自 serving.container_info（`build_predict_url`）；预测服务要求秒级规则时间戳（`api_schema.py::TimeSeriesPoint`、`pd.infer_freq` 失败即报错）、`MAX_PREDICTION_STEPS=1000`、`MAX_INPUT_DATA_POINTS=50000`；监控 RPC 返回毫秒时间戳（`to_monitor_epoch_ms`）；现有单工具调用超时 `TOOL_INVOKE_TIMEOUT` 默认 300s（`middleware/tool_runtime.py`）；predict HTTP 超时默认约 125s（`get_timeseries_predict_timeout_seconds`）。
- 验收标准：7 天磁盘爆满问题一次工具调用返回 50 台内的摘要排序且无整批超时丢失已完成结果；单台 7 天趋势返回约 168 个预测点；贴数据预测可用；无权限用户得到明确拒绝而非数据；返回中不出现 history 原始点。
