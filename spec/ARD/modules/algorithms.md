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
- `serving/service.py`：`@bentoml.service` 类，`@bentoml.api async predict(...)` + `health()`。
- `serving/models/loader.py`：MLflow 远程（`mlflow_model_uri`）/本地路径/DummyModel 三态加载。
- `training/mlflow_utils.py`：实验设置、模型日志、指标/参数、可视化、artifact 上传。
- `serving/metrics.py`：Prometheus 指标（加载/预测/耗时）。
- 端口 :3000（`make serving` → `bentoml serve ...`，BentoML 默认端口，Makefile 未显式绑定）。
- **打包配置不一致**：仅 `classify_object_detection_server/bentofile.yaml` 存在，其余 5 个服务无 `bentofile.yaml`（均有 `pyproject.toml`）【已实现，技术债】。
- 训练数据策略（见 `CLAUDE.md`）：传统 ML 合并 train+val 再训练；深度学习（图像/目标检测）保持 train/val 分离（YOLO 要求）。

## 4. 集成关系【已实现/已存在 / 推断】
- 后端 `apps/mlops` 通过 MLflow + AlgorithmConfig（Docker 镜像）管理训练；推理 serving_url 指向本服务【推断】。
- monitor 异常/无数据检测是否调用 anomaly 服务【待确认】。

## 5. 证据来源
`algorithms/classify_*_server/{serving/{service,models/loader,metrics}.py,training/mlflow_utils.py,bentofile.yaml,pyproject.toml}`、`algorithms/{AGENTS.md,DESIGN_GUIDE.md}`、`config/components/mlflow.py`。
