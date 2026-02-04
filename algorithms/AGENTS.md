# AGENTS.md - AI 编码助手指南

> Algorithms 模块：BK-Lite 机器学习算法服务集合

## 快速参考

| 服务类型 | 包管理器 | 开发命令 | 测试命令 |
|---------|---------|---------|---------|
| classify_*_server | `uv` | `make serving` | `uv run pytest` |

## 构建/测试/代码检查命令

### Python 项目（所有算法服务）

```bash
cd classify_{domain}_server

# 安装依赖
make install              # uv sync --all-groups --all-extras

# 训练模型
uv run classify_{domain}_server train \
    --dataset-path ./data/ \
    --config train.json

# 启动服务
make serving              # BentoML 服务 (端口 3000，支持热加载)

# 测试
uv run pytest                                                    # 完整测试套件
uv run pytest tests/test_models.py                              # 单个测试文件
uv run pytest tests/test_trainer.py::TestTrainer::test_fit -v   # 单个测试用例
uv run pytest -k "test_ecod" -x                                  # 按模式匹配 + 首次失败时停止
uv run pytest -s -v                                              # 显示标准输出 + 详细模式
```

### 使用训练脚本

```bash
cd classify_{domain}_server/support-files/scripts

# 配置环境变量
export MLFLOW_TRACKING_URI=http://mlflow:5000
export MINIO_ENDPOINT=http://minio:9000
export MINIO_ACCESS_KEY=your-key
export MINIO_SECRET_KEY=your-secret

# 从 MinIO 下载数据并训练
./train-model.sh datasets my_data.zip
./train-model.sh datasets my_data.zip configs/custom.json
```

## 代码风格

### Python

| 规则 | 值 |
|-----|---|
| 缩进 | 4 空格 |
| 行长度 | 150（建议保持在 120 以内）|
| 引号 | 双引号（字符串）|
| 类型提示 | 公共 API 必需，内部函数推荐 |
| 日志 | loguru |
| 文档字符串 | Google 风格 |

```python
# 推荐的代码风格
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from loguru import logger

from .base import BaseModel, ModelRegistry
from .preprocessing import DataPreprocessor


@ModelRegistry.register("MyModel")
class MyModel(BaseModel):
    """模型简短描述
    
    详细说明模型的功能、算法原理、使用场景等。
    
    参数说明：
    - param1: 参数1的说明
    - param2: 参数2的说明
    
    使用示例：
        model = MyModel(param1=value1)
        model.fit(train_data)
        predictions = model.predict(test_data)
    """
    
    def __init__(self, param1: float = 0.1, **kwargs):
        """初始化模型
        
        Args:
            param1: 参数1描述（默认值及范围说明）
            **kwargs: 其他参数
        """
        super().__init__(**kwargs)
        self.param1 = param1
        self.is_fitted = False
        
        # 参数验证
        if not 0 < param1 < 1.0:
            raise ValueError(f"param1 必须在 (0, 1.0) 之间，当前值: {param1}")
    
    def fit(self, 
            train_data: pd.DataFrame,
            val_data: Optional[pd.DataFrame] = None) -> "MyModel":
        """训练模型
        
        Args:
            train_data: 训练数据
            val_data: 验证数据（可选）
            
        Returns:
            self: 训练后的模型实例
            
        Raises:
            ValueError: 数据格式不正确
        """
        logger.info(f"开始训练，数据量: {len(train_data)}")
        
        # 提前返回模式（推荐）
        if train_data.empty:
            logger.warning("训练数据为空")
            return self
        
        # 训练逻辑
        self.is_fitted = True
        return self
```

### 导入顺序

**Python**:
```python
# 1. 标准库
from typing import Dict, List, Optional, Any
from pathlib import Path
import json

# 2. 第三方库
import pandas as pd
import numpy as np
import mlflow
from loguru import logger

# 3. 本地导入
from .base import BaseModel, ModelRegistry
from .preprocessing import DataPreprocessor
from ..config.loader import TrainingConfig
```

### 命名约定

| 类型 | 格式 | 示例 |
|-----|------|-----|
| 包名 | `classify_{domain}_server` | `classify_timeseries_server` |
| 类名 | `PascalCase` | `UniversalTrainer`, `ECODModel` |
| 函数名 | `snake_case` | `load_model`, `fit_transform` |
| 常量 | `UPPER_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| 私有方法 | `_snake_case` | `_validate_config`, `_preprocess_data` |
| 模型注册名 | `PascalCase` | `"GradientBoosting"`, `"Spell"`, `"ECOD"` |

## 错误处理

### Python

```python
from loguru import logger

# 推荐：具体异常类型 + 日志记录
try:
    result = load_data(path)
except FileNotFoundError as e:
    logger.error(f"数据文件不存在: {path}")
    raise ValueError(f"无法加载数据: {path}") from e
except pd.errors.ParserError as e:
    logger.exception("数据解析失败", extra={"path": path})
    raise

# 数据验证：提前返回
def process_data(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        logger.warning("输入数据为空")
        return pd.DataFrame()
    
    if "required_column" not in data.columns:
        raise ValueError("缺少必需列: required_column")
    
    # 处理逻辑
    return data

# 参数验证：快速失败
def __init__(self, contamination: float = 0.1):
    if not 0 < contamination < 1.0:
        raise ValueError(f"contamination 必须在 (0, 1.0) 之间，当前值: {contamination}")
    
    if contamination >= 0.5:
        logger.warning(f"contamination={contamination:.4f} >= 0.5，异常率过高")
```

## 架构模式

### 项目结构

```
classify_{domain}_server/
├── classify_{domain}_server/     # 主包
│   ├── cli/                      # 命令行接口（Fire）
│   │   └── bootstrap.py
│   ├── serving/                  # BentoML 在线服务
│   │   ├── service.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   └── models/loader.py
│   └── training/                 # 离线训练
│       ├── trainer.py            # UniversalTrainer
│       ├── data_loader.py
│       ├── mlflow_utils.py
│       ├── config/
│       │   ├── loader.py         # TrainingConfig
│       │   └── schema.py
│       ├── preprocessing/
│       │   ├── preprocessor.py
│       │   └── feature_engineering.py
│       └── models/
│           ├── base.py           # BaseModel + ModelRegistry
│           └── {model}_model.py
├── support-files/
│   ├── release/                  # Docker 部署
│   │   ├── Dockerfile
│   │   └── startup.sh
│   └── scripts/
│       ├── train.json            # 默认训练配置
│       └── train-model.sh        # 训练脚本
└── tests/
```

### 关键设计模式

#### 1. 模型注册机制

```python
# base.py
class ModelRegistry:
    _models = {}
    
    @classmethod
    def register(cls, name: str):
        def decorator(model_cls):
            cls._models[name] = model_cls
            return model_cls
        return decorator
    
    @classmethod
    def get(cls, name: str):
        if name not in cls._models:
            raise ValueError(f"未知模型: {name}")
        return cls._models[name]

# 使用
@ModelRegistry.register("ECOD")
class ECODModel(BaseAnomalyModel):
    pass

# 动态创建
model = ModelRegistry.get("ECOD")(**params)
```

#### 2. 配置驱动训练

```python
# 配置加载（单一职责）
class TrainingConfig:
    def __init__(self, config_path: str):
        if not Path(config_path).exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
        self._validate_config()

# CLI 注入环境变量
config = TrainingConfig(args.config)
config.set("mlflow", "tracking_uri", value=os.getenv("MLFLOW_TRACKING_URI"))

# 训练器使用配置
trainer = UniversalTrainer(config=config)
trainer.train(dataset_path)
```

#### 3. MLflow 集成

```python
# 标准流程
with mlflow.start_run(run_name=run_name) as run:
    # 记录参数
    mlflow.log_params(config.hyperparams)
    
    # 训练
    model.fit(train_data, val_data)
    
    # 记录指标
    metrics = model.evaluate(test_data)
    mlflow.log_metrics(metrics)
    
    # 保存模型
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=wrapper,
        artifacts=artifacts
    )
    
    # 注册模型
    model_uri = f"runs:/{run.info.run_id}/model"
    mlflow.register_model(model_uri, config.model_name)
```

## 训练数据策略差异说明

### Train/Val 数据合并策略

BK-Lite 算法模块中的不同服务采用了不同的训练数据策略，这是**有意的设计决策**，而非不一致性bug。

#### 策略对比

| 服务类型 | Train+Val合并 | 代码位置 | 原因 |
|---------|--------------|---------|------|
| **异常检测** (anomaly) | ✅ 合并 | trainer.py L546-554 | 传统ML算法，手动合并以利用更多数据 |
| **时间序列** (timeseries) | ✅ 合并 | trainer.py L111 | 传统ML算法，手动合并以利用更多数据 |
| **日志聚类** (log) | ✅ 合并 | trainer.py L464-467 | 传统ML算法，手动合并以利用更多数据 |
| **文本分类** (text) | ✅ 合并 | trainer.py L104-111 | 传统ML算法，手动合并以利用更多数据 |
| **图片分类** (image) | ❌ 不合并 | - | YOLO框架限制，遵循官方最佳实践 |
| **目标检测** (object_detection) | ❌ 不合并 | - | YOLO框架限制，遵循官方最佳实践 |

#### 设计理由

**传统ML算法（anomaly/timeseries/log/text）**：
- 使用 scikit-learn、pandas、numpy 等库
- 数据格式：DataFrame、ndarray、sparse matrix
- **合并策略**：在最终训练前手动合并 train+val 数据
  ```python
  # 示例：异常检测服务
  if val_data is not None:
      X_train = pd.concat([train_data[0], val_data[0]], axis=0)
      self.model.fit(X_train, y_train)  # 用 train+val 训练最终模型
  ```
- **优点**：利用更多数据（85% vs 70%），性能提升 5-15%
- **适用场景**：数据稀缺，需要榨取每一分性能

**深度学习算法（image/object_detection）**：
- 使用 Ultralytics YOLO 框架
- 数据格式：ImageFolder 目录结构 或 YAML 配置文件
- **分离策略**：保持 train/val 分离，遵循 YOLO 官方设计
  ```python
  # YOLO 训练流程
  model.train(
      data='data.yaml',  # 包含 train/val 分离的路径
      epochs=100,
      patience=20        # 基于 val 指标的 Early Stopping
  )
  ```
- **YOLO 框架行为**：
  - 在 train 数据上训练
  - 在 val 数据上验证（每个 epoch）
  - 使用 Early Stopping 防止过拟合
  - 保存 `best.pt`（基于 val 性能最佳的模型）
  - **不会自动合并 train+val 数据**
- **优点**：
  - 有独立的 val 集验证，防止过拟合
  - 符合 YOLO 官方最佳实践
  - 遵循深度学习社区标准
- **参考**：[Ultralytics YOLO 官方文档](https://docs.ultralytics.com/modes/train/)

#### 为什么不统一？

1. **框架限制**：YOLO 不支持自动合并 train+val，手动合并需要：
   - 图片分类：创建新的合并目录或软链接
   - 目标检测：修改 YAML 配置文件
   - 增加复杂度和维护成本

2. **最佳实践差异**：
   - 传统 ML：数据稀缺时，合并 train+val 是常见做法
   - 深度学习：数据充足时，保持分离更符合标准流程

3. **性能权衡**：
   - 合并策略：性能 +5-15%，但无独立 val 集验证
   - 分离策略：性能 -5-15%，但有独立 val 集防止过拟合

#### 如果需要修改策略

**将 YOLO 改为合并策略**（不推荐）：
```python
# 方案1：创建合并数据集
def merge_image_folders(train_path, val_path, output_path):
    """合并 train 和 val 目录"""
    # 创建软链接或复制文件
    pass

# 方案2：修改 YAML 配置
def create_merged_yaml(original_yaml):
    """创建合并后的 YAML 配置"""
    config = yaml.safe_load(open(original_yaml))
    config['train'] = 'images/train_and_val'  # 指向合并数据
    return config
```

**将传统ML改为分离策略**（不推荐）：
```python
# 移除 trainer.py 中的合并逻辑
# 直接传递 train_data 给 model.fit()
self.model.fit(train_data[0], train_data[1])  # 不合并 val_data
```

#### 总结

- ✅ **当前策略是合理的**：不同算法类型采用不同的最佳实践
- ✅ **代码已文档化**：注释中说明了合并的原因
- ✅ **性能已优化**：传统ML利用更多数据，YOLO遵循官方标准
- ⚠️ **如需统一**：需要权衡性能、复杂度、维护成本

---

## 关键规则

### 必须做

- 使用 `uv` 管理 Python 依赖
- 遵循现有代码库模式和架构
- 为公共函数添加类型提示
- 使用提前返回减少嵌套
- 在入口点、外部调用、异常处记录日志
- 配置文件必须完整（无代码内默认值）
- 环境变量用于运行时配置（如 `MLFLOW_TRACKING_URI`）

### 禁止做

- 添加未经批准的依赖
- 使用 `as any`、`@ts-ignore` 等类型抑制
- 提交机密信息或 `.env` 文件
- 主线程执行 CPU 密集操作
- 日志输出敏感信息
- 在训练代码中硬编码配置
- 空的 except 块 `except: pass`
- 删除失败的测试来"通过"

### 配置管理原则

```python
# ✅ 正确：配置外部化
class TrainingConfig:
    def __init__(self, config_path: str):  # 必需参数
        with open(config_path) as f:
            self.config = json.load(f)

# ❌ 错误：硬编码默认配置
DEFAULT_CONFIG = {"model": {...}}  # 不要这样做

# ✅ 正确：环境变量注入
os.getenv("MLFLOW_TRACKING_URI")  # 运行时配置

# ❌ 错误：配置文件中硬编码环境
{"mlflow": {"tracking_uri": "http://..."}}  # 不要这样做
```

## 提交前检查清单

1. **复用性**: 是否有现有模块/模式可用？
2. **最小化**: 是否为最小可运行变更？有回滚计划？
3. **兼容性**: API 输入/输出是否保持不变？
4. **依赖**: 是否添加了未批准的依赖？
5. **可观测性**: 关键路径是否有日志记录？
6. **安全性**: 是否有输入验证和权限检查？
7. **测试**: 测试是否通过？`uv run pytest`

## 关键依赖

| Python | 用途 |
|--------|------|
| bentoml | 模型服务 |
| mlflow | 实验跟踪和模型管理 |
| fire | CLI 框架 |
| loguru | 日志记录 |
| pandas, numpy | 数据处理 |
| scikit-learn | 机器学习基础 |
| feature-engine | 特征工程 |
| hyperopt | 超参数优化 |
| pyod | 异常检测（classify_anomaly_server）|
| ultralytics | YOLO 目标检测（classify_object_detection_server）|

## 提交约定

```
type(scope): subject

类型: feat, fix, docs, style, refactor, test, chore
范围: 模块名称
主题: 简明扼要的描述（中文或英文）

示例:
feat(trainer): 添加超参数优化支持
fix(ecod): 修复 contamination 参数验证
docs(readme): 更新安装说明
```

## 特定领域指南

### 添加新模型

1. 继承 `Base{Domain}Model` 抽象基类
2. 使用 `@ModelRegistry.register("ModelName")` 注册
3. 实现必需方法：`fit()`, `predict()`, `evaluate()`, `optimize_hyperparams()`
4. 在 `train.json` 中配置模型参数
5. 更新 `config/schema.py` 中的 `SUPPORTED_MODELS`

### 添加新特征工程

1. 在 `preprocessing/feature_engineering.py` 中添加方法
2. 在 `train.json` 的 `feature_engineering` 节配置参数
3. 通过 `use_feature_engineering` 开关控制启用
4. 在 `Trainer` 中集成特征工程器

### 环境变量配置

**必需**:
- `MLFLOW_TRACKING_URI`: MLflow 服务地址（训练时）

**MinIO 数据下载**（使用 train-model.sh 时）:
- `MINIO_ENDPOINT`: MinIO 服务地址
- `MINIO_ACCESS_KEY`: 访问密钥
- `MINIO_SECRET_KEY`: 私钥

## 参考实现

完整实现请参考现有服务：
- `classify_timeseries_server`: 时间序列预测（最完整）
- `classify_anomaly_server`: 异常检测
- `classify_log_server`: 日志聚类
- `classify_object_detection_server`: 目标检测
- `classify_text_classification_server`: 文本分类

---

**设计理念**: 渐进式设计，恰如其分，避免过度工程化
