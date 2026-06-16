# 模块 ARD：MLOps（机器学习生命周期）

> 路径 `server/apps/mlops` ｜ API 前缀 `api/v1/mlops/`

## 1. 职责【已实现/已存在】
管理 ML 数据集、训练任务、模型发布与服务；集成 MLflow 做实验跟踪。覆盖 6 类场景：异常检测、时序预测、日志聚类、分类、图像分类、目标检测。

## 2. 数据模型与存储【已实现/已存在】
每类场景含 **5 个场景实体**（类名带场景前缀，如 `AnomalyDetectionDataset`，见 `models/anomaly_detection.py:12,31,81,140,209`）+ 全局共享的 `AlgorithmConfig`：
| 实体 | 说明 |
|------|------|
| {Scenario}Dataset | 数据集容器（team 范围） |
| {Scenario}TrainData | 训练样本文件（存 MinIO `munchkin-public`，含 train/val/test 标记，TrainDataFileCleanupMixin） |
| {Scenario}TrainJob | 训练执行（algorithm/params/status/mlflow_run_id/model_version，TrainJobConfigSyncMixin） |
| {Scenario}DatasetRelease | 版本化数据集快照（ZIP 存 MinIO） |
| {Scenario}Serving | 模型服务实例（serving_url/model_version/status） |
| AlgorithmConfig（`models/algorithm_config.py`，**全局共享，非按场景**） | 算法注册（类型、Docker 镜像、表单配置） |

> 共享行为由 `models/mixins.py` 提供（`TrainJobConfigSyncMixin`、`TrainDataFileCleanupMixin`）。

**存储**：PostgreSQL（ORM）；MinIO（训练数据/ZIP/元数据）；MLflow（实验/指标/模型）。

## 3. 接口【已实现/已存在】
每场景注册 6 个 ViewSet：`{scenario}_{algorithm_configs,datasets,train_data,train_jobs,dataset_releases,servings}`，共 6×6=36 端点。

## 4. 依赖与通信【已实现/已存在】
- MLflow：`utils/mlflow_service.py`（实验命名、client，`MLFLOW_TRACKER_URL`）。
- Celery：`tasks/base.py:mark_release_as_failed`、`tasks/poll_train_job_status.py:poll_mlflow_train_job_status`（轮询 run 状态同步 TrainJob）。
- NATS：`nats_api.py` 提供 team 范围的数据访问模型映射，区分 `ROOT_MODULE_MODEL_MAP`（根团队对象）与 `INHERITED_MODULE_MODEL_MAP`（经 FK 如 `dataset__team` 继承的嵌套权限，`nats_api.py:47-114`）。
- 推理服务由 `algorithms/classify_*_server`（BentoML）承载，训练镜像来自 AlgorithmConfig。

## 5. 风险 / 待确认
- 训练任务的算力调度（Docker 容器如何拉起/编排）【待确认】。
- 与 `algorithms/` 服务的版本对齐与 serving_url 来源【推断为 BentoML 部署地址，需确认】。

## 6. 证据来源
`server/apps/mlops/{urls.py,models/*,utils/mlflow_service.py,tasks/*,nats_api.py}`、`config/components/mlflow.py`。
