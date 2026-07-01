# 模块 ARD：算法服务（BentoML）

> 路径 `algorithms/classify_*_server`

## 1. 职责【已实现/已存在】
以 BentoML 微服务承载 AI 推理能力，集成 MLflow 做模型加载与训练跟踪。

## 2. 服务清单【已实现/已存在】
| 服务 | 能力 |
|------|------|
| classify_anomaly_server | 时序异常检测（pyod/sklearn/hyperopt） |
| classify_timeseries_server | 时序预测 |
| classify_log_server | 日志聚类/模板提取 |
| classify_text_classification_server | 文本分类（NLP） |
| classify_image_classification_server | 图像分类（CNN） |
| classify_object_detection_server | 目标检测（YOLO/ultralytics/torch） |

## 3. 统一模式【已实现/已存在】
> 包目录为双层结构：`<server>/<server>/serving/...`（如 `classify_anomaly_server/classify_anomaly_server/serving/service.py`），以下相对路径均省略外层包目录。

- `serving/service.py`：`@bentoml.service` 装饰的服务类，6 个服务统一命名为 **`MLService`**；`health()` 入口同构。`predict` 请求/响应 schema 由各服务各自定义，并非全部统一为 `PredictResponse`：日志聚类服务当前返回 `LogClusterResponseV2`（`classify_log_server/serving/service.py:80-81`、`schemas/api_schema.py:101`）。该类名是对外/部署契约：`make serving` 入口固定为 `<pkg>.serving.service:MLService`。
- `serving/models/loader.py`：按 `config.source` 取值（`'mlflow'`/`'local'`/`'dummy'`）三态分发；各分支在缺参或加载失败时**于 loader 内部捕获并回退** `DummyModel`（如 `mlflow` 分支缺 `mlflow_model_uri` 或 `load_model` 异常时回退）。注意此回退发生在 loader 层，`load_model` 几乎不向上抛错；而服务 `service.py.__init__` 在确实捕获到加载异常时**默认不降级而是 `raise RuntimeError`**，仅当 `ALLOW_DUMMY_FALLBACK=true` 时才在服务层降级 `DummyModel`（开发/测试用）【已实现】。
- `serving/schemas/api_schema.py`：对外响应契约（`PredictResponse` 等），是 `predict` API 的返回类型。
- `serving/config/model_config.py`：`ModelConfig`（含 `source` 字段，驱动 loader 三态分发）。
- `serving/models/dummy_model.py`：`DummyModel` 占位模型；`serving/exceptions.py`：服务异常类型；`cli/bootstrap.py`：CLI 引导。
- `training/mlflow_utils.py`：以单一类 **`MLFlowUtils`** 的静态方法形式提供——实验设置（`setup_experiment`）、参数/指标批量日志（`log_params_batch`/`log_metrics_batch`）、artifact 上传（`log_artifact`）、可视化（`plot_*`）。
- `serving/metrics.py`：Prometheus 指标（加载/预测/耗时）。
- 端口 :3000（`make serving` → `bentoml serve ...`，BentoML 默认端口，Makefile 未显式绑定）。
- **打包配置不一致**：仅 `classify_object_detection_server/bentofile.yaml` 存在，其余 5 个服务无 `bentofile.yaml`（均有 `pyproject.toml`）【已实现，技术债】。
- 训练数据策略（见 `CLAUDE.md`）：传统 ML 合并 train+val 再训练；深度学习（图像/目标检测）保持 train/val 分离（YOLO 要求）。

## 4. 运行安全配置【已实现/已存在】
- 异常检测服务：`PREDICT_MAX_DATA_POINTS` 限制单次预测数据点数（`classify_anomaly_server/serving/schemas/api_schema.py:8-9`），服务层在预测入口执行上限校验（`service.py:148`）。
- 时序预测服务：`MAX_PREDICTION_STEPS` 与 `MAX_INPUT_DATA_POINTS` 分别限制预测步长与输入数据点（`classify_timeseries_server/serving/schemas/api_schema.py:9-11`），服务层在预测入口执行上限校验（`service.py:222`）。
- 本地模型加载支持 `MODEL_SHA256` 校验：异常检测与日志聚类 loader 在配置该环境变量时校验本地模型文件摘要；未配置时不强制校验（`classify_anomaly_server/serving/models/loader.py:84`、`classify_log_server/serving/models/loader.py:80`）。

## 5. 集成关系【已实现/已存在 / 推断】
- 后端 `apps/mlops` 通过 MLflow + AlgorithmConfig（Docker 镜像）管理训练；推理 serving_url 指向本服务【推断】。
- monitor 异常/无数据检测是否调用 anomaly 服务【待确认】。

## 2026-07-01 Code-ARD 校准
- `[algorithms#20260701-034]` 修正 predict 契约描述：保留 `MLService`/`health`/Makefile 入口统一结论，但 `predict` schema 按服务分化，日志聚类返回 `LogClusterResponseV2`。
- `[algorithms#20260701-035]` 补录请求上限与本地模型 SHA256 校验配置。

## 6. 证据来源
> 注意双层包目录：源码实为 `algorithms/<server>/<server>/serving/...`（如 `algorithms/classify_anomaly_server/classify_anomaly_server/serving/service.py`）。

- 服务类统一命名 `MLService` 与部署入口：`algorithms/classify_anomaly_server/classify_anomaly_server/serving/service.py:20-24`（`@bentoml.service` 装饰 `class MLService`）、`:103`（`predict(...) -> PredictResponse`）；`algorithms/classify_anomaly_server/Makefile:18`（`bentoml serve classify_anomaly_server.serving.service:MLService`）；其余 5 服务同名 `MLService` 且 Makefile:18 入口同构（`classify_timeseries_server`/`classify_log_server`/`classify_text_classification_server`/`classify_image_classification_server`/`classify_object_detection_server` 的 `serving/service.py` 与各自 `Makefile:18`）。日志聚类响应例外：`algorithms/classify_log_server/classify_log_server/serving/service.py:80-81`、`serving/schemas/api_schema.py:101`。
- loader 按 `config.source` 三态分发 + 分支内回退：`algorithms/classify_anomaly_server/classify_anomaly_server/serving/models/loader.py:14-38`（`if config.source == 'mlflow'/'local'/'dummy'`）、`:43-45` 与 `:59-62`（`mlflow` 分支缺参/异常回退 `DummyModel`）、`:67-69` 与 `:85-88`（`local` 分支缺参/异常回退）。
- 服务层降级受 `ALLOW_DUMMY_FALLBACK` 门控、默认抛错：`algorithms/classify_anomaly_server/classify_anomaly_server/serving/service.py:58-86`（`except` 中 `os.getenv("ALLOW_DUMMY_FALLBACK")` 为真才用 `DummyModel`，否则 `raise RuntimeError`）。
- serving 稳定子结构：`serving/schemas/api_schema.py:93`（`class PredictResponse`）、`serving/config/model_config.py:9`（`class ModelConfig`）、`serving/models/dummy_model.py`、`serving/exceptions.py`、`cli/bootstrap.py`（均以 `classify_anomaly_server` 双层包为例）。
- `MLFlowUtils` 类静态方法：`algorithms/classify_anomaly_server/classify_anomaly_server/training/mlflow_utils.py:24`（`class MLFlowUtils`）、`:28`（`setup_experiment`）、`:108`（`log_params_batch`）、`:167`（`log_metrics_batch`）、`:193`（`log_artifact`）、`:209`/`:352`/`:409`/`:468` 等（`plot_*`）。
- 其余：`algorithms/classify_*_server/.../serving/metrics.py`、`bentofile.yaml`、`pyproject.toml`；`algorithms/{AGENTS.md,DESIGN_GUIDE.md}`；`config/components/mlflow.py`。
- 运行安全配置：`algorithms/classify_anomaly_server/classify_anomaly_server/serving/schemas/api_schema.py:8-9`、`serving/service.py:148`、`serving/models/loader.py:84`；`algorithms/classify_timeseries_server/classify_timeseries_server/serving/schemas/api_schema.py:9-11`、`serving/service.py:222`；`algorithms/classify_log_server/classify_log_server/serving/models/loader.py:80`。
