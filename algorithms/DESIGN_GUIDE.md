# Algorithms 模型服务设计指南

> 本指南用于指导新模型算法服务的设计与实现，确保架构一致性和代码质量。
>
> 更新时间：2026年1月8日 - v1.3


## 📐 设计原则

### 核心原则：渐进式设计，恰如其分

1. **最小可用**：首先实现核心功能（训练+服务），确保端到端可用
2. **避免过早抽象**：不提前设计未来可能需要的功能（见下方详细说明）
3. **易于扩展**：通过清晰的抽象支持后续功能添加
4. **统一架构**：遵循现有三个服务的架构模式

---

### 🚫 避免过早抽象（Anti-Premature Abstraction）

**核心理念**：
- ✅ **先实现，后抽象**：等真正需要时再提取公共逻辑
- ✅ **务实设计**：代码重复优于错误的抽象
- ✅ **明确职责**：基类定义接口契约，不实现业务逻辑

---

## 🏗️ 标准项目结构

```
algorithms/
└── classify_{domain}_server/          # 模型服务根目录
    ├── README.md                       # 项目说明（简洁即可）
    ├── Makefile                        # 构建和运行脚本
    ├── pyproject.toml                  # Python项目配置（uv管理依赖）
    ├── pytest.ini                      # 测试配置
    ├── .env.example                    # 环境变量示例
    ├── .gitignore                      # Git忽略文件
    ├── mc                              # MinIO Client 二进制（用于数据下载，开发者手动引入，无需下载）
    │
    ├── classify_{domain}_server/       # 主包
    │   ├── __init__.py
    │   │
    │   ├── cli/                        # 命令行接口
    │   │   ├── __init__.py
    │   │   └── bootstrap.py            # CLI入口（使用fire）
    │   │
    │   ├── serving/                    # 在线服务层
    │   │   ├── __init__.py
    │   │   ├── service.py              # BentoML服务定义
    │   │   ├── config.py               # 服务配置
    │   │   ├── schemas.py              # API Schema（Pydantic）
    │   │   ├── exceptions.py           # 自定义异常
    │   │   ├── metrics.py              # Prometheus指标
    │   │   └── models/                 # 模型加载器
    │   │       ├── __init__.py
    │   │       ├── loader.py           # 统一模型加载
    │   │       └── dummy_model.py      # 降级策略，加载模型失败时使用，可选
    │   │
    │   └── training/                   # 离线训练层
    │       ├── __init__.py
    │       ├── trainer.py              # 通用训练器
    │       ├── data_loader.py          # 数据加载
    │       ├── mlflow_utils.py         # MLflow工具函数
    │       ├── config/                 # 训练配置
    │       │   ├── __init__.py
    │       │   └── loader.py           # 配置加载器
    │       ├── preprocessing/          # 数据预处理
    │       │   ├── __init__.py
    │       │   ├── preprocessor.py     # 基础预处理器
    │       │   └── feature_engineering.py  # 特征工程（必选，每个算法领域都需要实现基础版本，但是训练时可选是否在训练过程中启用）
    │       └── models/                 # 训练模型实现
    │           ├── __init__.py
    │           ├── base.py             # 抽象基类 + ModelRegistry
    │           ├── {algorithm}_model.py # 具体模型实现
    │           └── {algorithm}_wrapper.py # MLflow推理包装器（可选）
    │
    ├── support-files/                  # 支持文件
    │   ├── release/                    # 发布相关文件
    │   │   ├── Dockerfile              # 容器镜像定义
    │   │   ├── startup.sh              # 容器启动脚本
    │   │   └── supervisor/             # Supervisor进程管理配置
    │   │       ├── supervisord.conf
    │   │       └── conf.d/
    │   │           ├── bentoml.conf    # BentoML服务配置
    │   │           └── mlflow.conf     # MLflow UI配置
    │   ├── scripts/                    # 脚本目录
    │   │   ├── train.json              # 默认训练配置
    │   │   ├── train-model.sh          # 训练执行脚本（MinIO下载+训练）
    │   │   ├── test-predict.sh         # 预测测试脚本
    │   │   └── data/                   # 训练时数据目录（运行时创建）
    │   │       ├── downloads/          # MinIO下载的压缩包
    │   │       ├── datasets/           # 解压后的数据集
    │   │       └── configs/            # 从MinIO下载的配置
    │   └── train.json.example          # 训练配置示例（文档参考）
    │
    └── tests/                          # 测试用例
        ├── __init__.py
        ├── conftest.py                 # pytest配置和fixtures
        └── test_*.py                   # 测试文件
```

### 关键目录说明

#### 1. `classify_{domain}_server/` - 主包
- **cli/**: 命令行工具（`train`, `serve`）
- **serving/**: 在线服务（BentoML + Prometheus监控）
- **training/**: 离线训练（Trainer + MLflow集成）

#### 2. `support-files/` - 支持文件
- **release/**: 容器化部署相关
  - `Dockerfile`: 统一的镜像构建（Python 3.12 + uv + fonts）
  - `startup.sh`: 容器启动入口
  - `supervisor/`: 进程管理配置（服务+MLflow UI）
- **scripts/**: 训练和测试脚本
  - `train.json`: 默认训练配置
  - `train-model.sh`: 自动化训练流程（MinIO下载+解压+训练）
  - `data/`: 运行时数据目录（不纳入版本控制）

#### 3. 数据流向

**数据集流向**：
```
MinIO (datasets bucket)
  ↓ train-model.sh 下载
scripts/data/downloads/*.zip
  ↓ unzip
scripts/data/datasets/*_data.csv (文件格式不固定，不同训练类型会有对应的格式)
  ↓ Trainer 读取
training/data_loader.py
  ↓ 预处理
training/preprocessing/
  ↓ 训练
training/models/
  ↓ 保存
MLflow Model Registry
  ↓ 加载
serving/models/loader.py
  ↓ 预测
serving/service.py
```

**配置文件流向**：
```
train-model.sh 接收 CONFIG 参数
  ├─ 传入路径 → 使用指定配置（本地或MinIO路径）
  └─ 未传入 → 使用默认配置（./train.json）
       ↓
CLI bootstrap.py (--config 参数)
       ↓ 验证文件存在
TrainingConfig.from_file()
       ↓ 加载配置
UniversalTrainer(config_obj)
       ↓ 应用配置
模型训练（超参数、预处理、特征工程等）
```

---

## 🔄 统一训练流程

### UniversalTrainer 核心设计

**标准10步训练流程**：
1. MLflow 实验设置
2. 数据加载（支持目录/文件模式）
  - 目录模式：传递的路径是目录，一般包含三个文件 train_data val_data test_data 文件类型视训练类型而定
  - 文件模式：传递的路径是具体文件路径，需要在数据预处理时进行分割成train_data val_data test_data，分割比例代码写死固定比例
3. 数据预处理
4. 模型实例化（通过 ModelRegistry 动态加载）
5. 开始 MLflow run
6. 记录配置参数
7. 超参数优化（使用 Hyperopt）
8. 模型训练
9. 模型评估（train/val/test）
10. 模型保存和注册
   - `self._save_model_to_mlflow(model, metrics)`: 保存模型到 MLflow
   - `self._register_model(model_uri)`: 注册模型到 MLflow Model Registry

**超参数优化架构**（Trainer 调度，Model 实现）：

```python
def _optimize_hyperparams(self, train_data, val_data) -> Optional[Dict[str, Any]]:
    """超参数优化统一调度
    
    架构：Trainer 负责配置检查和错误处理，Model 实现具体优化逻辑
    
    val_data 参数用途说明：
    - 不用于模型训练（model.fit() 不使用）
    - 仅用于超参数优化时的目标函数评估
    - 在 optimize_hyperparams() 中训练临时模型并在 val_data 上评估性能
    
    三种使用模式：
    1. 时间序列（Prophet/RandomForest）：
       - fit(train_data, val_data, merge_val=False)  # 只用训练集训练
       - evaluate(val_data, is_in_sample=False)      # 验证集评估（样本外）
       
    2. 日志聚类（Spell）：
       - fit(train_data)                              # 无监督训练，不使用验证集
       - evaluate(val_data)                           # 验证集评估（模板质量）
       
    3. 异常检测（ECOD）：
       - fit(train_data)                              # 无监督训练
       - evaluate(val_data, val_labels)               # 验证集评估（需要标签）
    """
    # 1. 检查是否启用（max_evals=0 表示跳过）
    max_evals = getattr(self.config, 'max_evals', 0)
    if max_evals == 0:
        return {}
    
    # 2. 调用模型的优化方法（使用 Hyperopt）
    try:
        return self.model.optimize_hyperparams(train_data, val_data, max_evals)
    except Exception as e:
        logger.error(f"优化失败: {e}")
        return {}
```

**关键方法**：
- `_create_model()`: 通过 ModelRegistry 动态创建模型实例
- `_preprocess_data()`: 数据预处理（子类实现）
- `_optimize_hyperparams()`: 统一的超参数优化调度
- `_evaluate_train_fitting()`: 评估训练集拟合度
- `_evaluate_test()`: 评估测试集性能
- `_save_model_to_mlflow()`: 保存模型为 MLflow 格式

详细实现请参考现有项目：`classify_timeseries_server/training/trainer.py`

---

## 🎯 模型基类设计

### 核心设计原则

**基类职责**：
- ✅ **定义接口契约**：通过 `@abstractmethod` 声明必须实现的方法
- ✅ **提供工具方法**：如 `get_params()`、`_check_fitted()` 等通用辅助
- ❌ **不实现业务逻辑**：不在基类中实现具体的评估、预处理等逻辑

### 统一接口定义

**必须实现的抽象方法**：
- `fit(train_data, val_data, **kwargs)`: 训练模型
- `predict(X)`: 模型预测
- `evaluate(test_data, ground_truth, prefix="test")`: 评估性能，返回指标字典
- `optimize_hyperparams(train_data, val_data, max_evals)`: 超参数优化（使用 Hyperopt）

**可选工具方法**：
- `get_params()`: 获取模型参数
- `_check_fitted()`: 检查模型是否已训练

**ModelRegistry 注册机制**：
```python
@ModelRegistry.register("my_model")
class MyModel(Base{Domain}Model):
    ...

# 动态创建
model = ModelRegistry.get("my_model")(**params)
```

**命名规范**：
- 时间序列：`BaseTimeSeriesModel`
- 日志分析：`BaseLogClusterModel`
- 异常检测：`BaseAnomalyModel`

**评估指标要求**：
- 返回格式：`{f"{prefix}_metric_name": value}`
- 命名规范：小写下划线（rmse、mae、f1、precision、recall）
- 内部数据用 `_` 前缀（不会被 MLflow 记录）

**完整实现参考**：
- `classify_timeseries_server/training/models/base.py`
- `classify_anomaly_server/training/models/base.py`
- `classify_log_server/training/models/base.py`

### 模型保存与注册

**训练完成后自动执行两步**：

1. **保存到 MLflow**：模型类实现 `save_mlflow(artifact_path="model")` 方法
   - 创建 MLflow pyfunc Wrapper（如需要）
   - 调用 `mlflow.pyfunc.log_model()` 保存模型和 artifacts

2. **注册到 Model Registry**：Trainer 实现 `_register_model(model_uri)` 方法
   - 默认启用，无需配置开关
   - 使用 `config.model_name` 作为注册名称
   - 每次训练自动递增版本号

**配置示例**：
```json
{
  "model": {
    "type": "Spell",
    "name": "spell_log_clustering"  // Model Registry 注册名
  },
  "mlflow": {
    "experiment_name": "log_clustering_spell"  // 实验名(一般与model.name一致)
  }
}
```

**参考实现**：
- 保存：`classify_log_server/training/models/spell_model.py` - `save_mlflow()` 
- 注册：`classify_anomaly_server/training/trainer.py` - `_register_model()`

---

### MLflow 推理包装器（Wrapper）

**何时需要**：
- ✅ 推理需要额外的预处理/后处理逻辑
- ✅ 需要在推理时使用特征工程器
- ✅ 推理逻辑与训练差异大（如递归预测）
- ❌ 简单 sklearn 模型可直接用 `mlflow.sklearn.log_model()`

**核心作用**：
- 继承 `mlflow.pyfunc.PythonModel`
- 实现 `predict(context, model_input)` 方法（**不加类型提示**，避免警告）
- 封装完整推理流程（解析输入 → 特征工程 → 预测 → 后处理）

**参考实现**：
- `classify_timeseries_server/training/models/gradient_boosting_wrapper.py`
- `classify_log_server/training/models/spell_wrapper.py`

---

## 🚀 BentoML 服务设计

### 核心设计要点

**服务结构**：
- `@bentoml.service`: 服务装饰器，配置超时等参数
- `@bentoml.on_deployment`: 全局初始化（执行一次）
- `__init__()`: 服务实例初始化（加载配置和模型）
- `@bentoml.on_shutdown`: 服务关闭时的清理
- `@bentoml.api`: API 端点定义

**关键功能**：
1. **模型加载**：支持本地文件和 MLflow Registry
2. **配置验证**：启动时快速失败（Fast Fail）
3. **监控指标**：Prometheus metrics（加载次数、预测次数、延迟）
4. **错误处理**：统一的异常处理和日志记录
5. **DummyModel**：当加载模型失败时的降级策略(可选，可自主选择加载模型失败时是报错，还是使用降级策略)

**必需的 API 端点**：
- `predict()`: 主要预测接口（使用 Pydantic schemas）
- `health()`: 健康检查接口

详细实现请参考现有项目的 `serving/service.py`。

---

## 📝 配置文件设计

### 配置结构说明

**核心原则**：
- 使用扁平化结构，避免过度嵌套
- 包含必要的注释字段（`_comment`、`_desc`）
- 提供合理的默认值
- 支持超参数搜索空间定义
- **配置外部化**：配置应存储在文件中，而非代码中硬编码

**必需的顶层字段**：
1. `model`: 模型配置（type, name）
2. `hyperparams`: 超参数配置（含搜索空间，含 `use_feature_engineering` 开关）
3. `preprocessing`: 数据预处理配置
4. `feature_engineering`: 特征工程配置（必须实现，训练时由 `use_feature_engineering` 控制）
5. `mlflow`: MLflow 实验跟踪配置（可选，推荐使用环境变量）

### 配置加载策略

**推荐方式：单一文件模式 + 职责分离**

```python
class TrainingConfig:
    def __init__(self, config_path: str):
        """从文件加载配置
        
        Args:
            config_path: 配置文件路径（必需参数）
        
        Raises:
            FileNotFoundError: 配置文件不存在
        """
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
        self._validate_config()
```

**设计理念（职责分离）**：
- ✅ **配置外部化**：配置存储在文件中，便于版本控制
- ✅ **职责清晰**：train-model.sh 管理配置来源，Python代码只负责加载
- ✅ **无硬编码**：代码中不保存任何默认路径或默认配置
- ✅ **符合单一职责原则**：每个组件只做一件事

**职责划分**：

| 组件 | 职责 |
|------|------|
| **train-model.sh** | • 决定配置文件路径（默认 ./train.json）<br>• 从 MinIO 下载配置（如需要）<br>• 传递明确路径给 CLI |
| **CLI (bootstrap.py)** | • 接收配置路径参数（必需）<br>• 传递给 TrainingConfig |
| **TrainingConfig** | • 加载给定路径的配置文件<br>• 验证配置正确性<br>• 提供配置访问接口 |

**配置来源管理流程**：
```
train-model.sh 接收 CONFIG 参数
  ├─ 参数传入 → 使用指定配置
  └─ 参数未传入 → 使用默认配置（./train.json）
       ↓
train-model.sh 准备配置文件
  ├─ MinIO 路径 → 下载到本地
  └─ 本地路径 → 检查文件存在性
       ↓
train-model.sh 调用 CLI（总是传入明确路径）
  uv run classify_{domain}_server train \
      --dataset-path=... \
      --config="$CONFIG"
       ↓
CLI 接收 --config 参数（必需）
       ↓
TrainingConfig(config_path)  # config_path 是必需参数
       ↓
加载并验证配置文件
```

**配置文件存放位置**：
```
support-files/
  ├── train.json.example        # 详细示例（文档参考，带大量注释）
  └── scripts/
      ├── train.json             # 默认配置（train-model.sh 使用）
      └── data/                  # 运行时数据目录
```

**重要说明**：
- ✅ `train.json` 是完整配置，包含所有必需字段
- ✅ 代码中不存在 `DEFAULT_CONFIG` 字典
- ✅ 配置文件是配置的唯一真实来源
- ✅ train-model.sh 决定使用哪个配置文件

**测试环境配置**：
```
tests/
  └── fixtures/
      └── test_config.json      # 测试专用配置（完整配置）
```

### 配置示例
大体结构，具体参数由类型实现而定
具体参考各类型具体实现的support-files文件夹中的示例文件
```json
{
  "model": {
    "type": "模型类型标识符（对应 ModelRegistry 注册名）",
    "name": "模型名称（用于 MLflow 记录）"
  },
  
  "hyperparams": {
    "use_feature_engineering": "是否启用特征工程（布尔值）",
    "random_state": "随机种子（整数）",
    "max_evals": "超参数搜索次数（0表示跳过）",
    "metric": "优化目标指标名称",
    "search_space": {
      "param_name": ["候选值列表"]
    }
  },
  
  "feature_engineering": {
    "...": "特征工程详细配置（由 use_feature_engineering 控制是否启用）"
  },
  
  "preprocessing": {
    "...": "预处理配置"
  },
  
  "mlflow": {
    "experiment_name": "实验名称"
  }
}
```

**配置验证**：

实现4层验证机制，确保配置的正确性和完整性：

```python
def _validate_config(self):
    """配置验证（推荐实现4层）"""
    # Layer 1: 结构完整性校验
    self._validate_structure()
    
    # Layer 2: 必需字段 + 基本类型校验
    self._validate_required_fields()
    
    # Layer 3: 业务规则校验
    self._validate_business_rules()
    
    # Layer 4: 依赖关系校验
    self._validate_dependencies()
```

**验证层次说明**：
- **Layer 1**: 检查必需的顶层字段是否存在
- **Layer 2**: 检查字段类型和必填项
- **Layer 3**: 检查参数值的合理性（如范围、枚举值）
- **Layer 4**: 检查条件依赖（如 `use_feature_engineering=true` 时必须提供 `feature_engineering` 配置）

**注意**：
- ✅ 前两层为最小验证要求
- ✅ 后两层可根据项目复杂度选择性实现
- ⚠️ 验证失败应立即抛出异常（Fast Fail）
- ⚠️ 由于没有代码默认值，配置文件必须完整

---

### 配置Schema定义

**schema.py 的作用**：

```python
"""配置文件 Schema 定义"""

from typing import List

# ✅ 定义支持的枚举值（用于验证）
SUPPORTED_MODELS: List[str] = [
    "model_type_1",
    "model_type_2",
]

SUPPORTED_METRICS: List[str] = [
    "metric_1",
    "metric_2",
]

# ❌ 不再定义 DEFAULT_CONFIG
# 原因：配置应该外部化，不在代码中硬编码
```

**设计原则**：
- ✅ 只定义枚举常量和验证规则
- ❌ 不定义默认配置字典
- ❌ 不定义默认文件路径

---

## 🔧 CLI 设计

### 核心命令

**train 命令**：
- 参数：
  - `--dataset-path`: 数据集路径（目录或文件，必需）
  - `--config`: 配置文件路径（必需）
  - `--run-name`: MLflow run 名称（可选）
- 环境变量：`MLFLOW_TRACKING_URI`（必需）

**使用示例**：
```bash
# 基本训练
export MLFLOW_TRACKING_URI=http://mlflow:5000
classify_{domain}_server train \
    --dataset-path ./data/ \
    --config train.json

# 自定义run名称
classify_{domain}_server train \
    --dataset-path ./data/ \
    --config custom.json \
    --run-name my_experiment_v1
```

**关键逻辑**：
1. 检查环境变量和配置文件存在性（Fast Fail）
2. 加载配置：`TrainingConfig.from_file(config)`
3. 创建训练器：`UniversalTrainer(config_obj)`
4. 执行训练：`trainer.train(dataset_path)`

**完整实现参考**：`classify_*/cli/bootstrap.py`

---

## 🐳 Docker 部署配置

### 关键要点

所有服务使用统一 Dockerfile：`support-files/release/Dockerfile`

**核心配置**：
- 基础镜像：`python:3.12`
- 包管理：`uv`（Python包管理工具）
- 系统组件：`supervisor`（进程管理）、`fonts-wqy-zenhei`（中文字体）
- 构建参数：`NEXUS_PYTHON_REPOSITY`（可选，私有镜像源）
- 入口点：`startup.sh`（启动 BentoML + MLflow UI）

**部署结构**：
- Supervisor 管理多进程：
  - `supervisord.conf`: 主配置
  - `conf.d/bentoml.conf`: BentoML 服务
  - `conf.d/mlflow.conf`: MLflow UI

---

## 📜 训练脚本标准实现

### train-model.sh 核心要点

位置：`support-files/scripts/train-model.sh`

**核心功能**：
1. 从 MinIO 下载数据集（ZIP格式）
2. 解压到本地目录
3. 管理配置文件路径（默认 ./train.json，或从 MinIO 下载）
4. 调用 CLI 训练命令（总是传入明确的配置路径）
5. 可选的清理操作

**参数接口**：
```bash
./train-model.sh [BUCKET] [DATASET] [CONFIG]

# 示例
./train-model.sh datasets my_data.zip
./train-model.sh datasets my_data.zip configs/train.json
```

**必需的环境变量**：
```bash
export MINIO_ENDPOINT=http://minio-server:9000
export MINIO_ACCESS_KEY=your-access-key
export MINIO_SECRET_KEY=your-secret-key
export MLFLOW_TRACKING_URI=http://mlflow:15000
```

**脚本核心逻辑**：
1. 环境检查（uv, python, unzip, mc）
2. MinIO 连接配置
3. 下载并解压数据集
4. 准备配置文件（MinIO或本地）
5. 执行训练：`uv run classify_{domain}_server train --dataset-path=... --config=...`
6. 错误处理和日志记录

详细实现请参考现有项目的 `support-files/scripts/train-model.sh`

---

## ✅ 实现检查清单

### 必须实现的组件

- [ ] 项目结构按标准模板创建
- [ ] `Base{Domain}Model` 抽象基类
- [ ] `ModelRegistry` 注册机制
- [ ] 至少一个具体模型实现
- [ ] `UniversalTrainer` 训练器
- [ ] 数据加载器（支持目录/文件模式）
- [ ] 数据预处理器
- [ ] BentoML 服务定义
- [ ] Pydantic Schema 定义
- [ ] `DummyModel` 实现 (可选)
- [ ] CLI 接口（train/serve命令）
- [ ] `train.json` 默认配置
- [ ] `MLFlowUtils` 工具函数
- [ ] Prometheus 指标定义
- [ ] README.md 文档
- [ ] 超参数优化（Hyperopt）
- [ ] 特征工程模块
- [ ] 模型可视化


---

## 🎨 代码风格规范

### 命名约定

- **包名**: `classify_{domain}_server`（小写+下划线）
- **类名**: `PascalCase`（如 `UniversalTrainer`）
- **函数名**: `snake_case`（如 `load_model`）
- **常量**: `UPPER_CASE`（如 `MAX_RETRIES`）
- **私有方法**: `_snake_case`（如 `_validate_config`）
-- **模型注册名**: `PascalCase`（如 `GradientBoosting`,`Spell`,特殊的：`ECOD`(全大写,缩写特例)）

---

## 📚 参考实现

查看现有三个服务的实现：

- **classify_anomaly_server**: 异常检测（PyOD）
- **classify_log_server**: 日志聚类（logparser3）
- **classify_timeseries_server**: 时间序列（Prophet/sklearn）

**推荐学习路径**：

1. 先阅读 `classify_timeseries_server`（最完整）
2. 对比 `classify_anomaly_server`（了解异常检测特性）
3. 参考 `classify_log_server`（了解文本处理）

---

## 📌 设计原则总结

1. **统一架构**：遵循现有三个服务的模式
2. **渐进式设计**：先实现核心功能，再扩展
3. **避免过早抽象**：等真正需要时再提取公共逻辑
4. **配置驱动**：通过配置切换模型和参数
5. **完善文档**：代码即文档，注释清晰
6. **容错机制**：启动时配置验证，运行时异常处理
7. **可观测性**：Prometheus 指标 + 详细日志
---

