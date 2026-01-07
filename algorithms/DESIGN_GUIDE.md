# Algorithms 模型服务设计指南

> 本指南用于指导新模型算法服务的设计与实现，确保架构一致性和代码质量。
>
> 更新时间：2026年1月7日

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

**超参数优化架构**（Trainer 调度，Model 实现）：

```python
def _optimize_hyperparams(self, train_data, val_data) -> Optional[Dict[str, Any]]:
    """超参数优化统一调度
    
    架构：Trainer 负责配置检查和错误处理，Model 实现具体优化逻辑
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

```python
"""模型基类 - 标准接口定义"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
import pandas as pd
import numpy as np
from loguru import logger


class Base{Domain}Model(ABC):
    """模型基类 - 定义统一接口
    
    设计原则：
    1. 基类只定义接口契约（@abstractmethod）
    2. 不实现具体的业务逻辑（如评估算法）
    3. 子类完整实现各自的评估逻辑
    
    必须实现的核心方法：
    - fit(): 训练模型
    - predict(): 预测
    - evaluate(): 评估性能
    - optimize_hyperparams(): 超参数优化
    
    可选实现的方法：
    - get_params(): 获取模型参数
    - save()/load(): 模型持久化
    
    命名规范：
    {Domain} 应替换为算法领域的 PascalCase 单词，例如：
    - 时间序列：BaseTimeSeriesModel
    - 日志分析：BaseLogClusterModel
    - 异常检测：BaseAnomalyModel
    """
    
    def __init__(self, **kwargs):
        """初始化模型
        
        Args:
            **kwargs: 模型特定的参数
        """
        self.model = None
        self.config = kwargs
        self.is_fitted = False
    
    @abstractmethod
    def fit(self, 
            train_data: Any,
            val_data: Optional[Any] = None,
            **kwargs) -> 'Base{Domain}Model':
        """训练模型
        
        Args:
            train_data: 训练数据
            val_data: 验证数据（可选）
            **kwargs: 额外参数
            
        Returns:
            self: 训练后的模型实例
        """
        pass
    
    @abstractmethod
    def predict(self, X: Any) -> np.ndarray:
        """预测
        
        Args:
            X: 输入数据
            
        Returns:
            预测结果
            
        Raises:
            RuntimeError: 模型未训练
        """
        pass
    
    @abstractmethod
    def evaluate(self, 
                 test_data: Any,
                 ground_truth: Optional[Any] = None,
                 prefix: str = "test") -> Dict[str, float]:
        """评估模型性能（⚠️ 子类必须完整实现）
        
        设计要求：
        1. 各模型实现自己的评估逻辑，不调用基类方法
        2. 根据算法特性选择合适的评估指标
        3. 返回的指标应与任务类型匹配
        
        Args:
            test_data: 测试数据（格式由子类定义）
            ground_truth: 真实标签（监督任务使用，可选）
            prefix: 指标名称前缀（默认"test"）
            
        Returns:
            评估指标字典，格式: {f"{prefix}_metric_name": value}
            
        示例：
            # 日志聚类
            {"test_num_templates": 50, "test_coverage_rate": 0.95}
            
            # 异常检测
            {"test_precision": 0.85, "test_recall": 0.78, "test_f1": 0.81}
            
            # 时序预测
            {"test_rmse": 12.5, "test_mae": 8.3, "test_mape": 0.15}
            
        注意：
        - 内部数据使用 _ 前缀（如 _predictions, _y_true）
        - 以 _ 开头的字段不会被 MLflow 记录
        - 各模型的评估逻辑完全独立，保持自治
        
        评估指标命名规范：
        - 统一使用小写下划线（snake_case）
        - 优先使用行业标准缩写（如 rmse、mae、f1、auc、precision、recall）
        - 自定义指标使用描述性英文单词（如 num_templates、coverage_rate）
        - 避免混用缩写和全称（如 precision_f1score）
        """
        pass
    
    @abstractmethod
    def optimize_hyperparams(
        self,
        train_data: Any,
        val_data: Any,
        max_evals: int,
        **kwargs
    ) -> Dict[str, Any]:
        """超参数优化（必须实现）
        
        使用 Hyperopt 进行贝叶斯优化，寻找最优超参数组合。
        
        Args:
            train_data: 训练数据
            val_data: 验证数据
            max_evals: 最大评估次数
            **kwargs: 额外参数
            
        Returns:
            最优超参数字典
            
        实现要求：
        1. 定义搜索空间（从 self.config 读取 search_space）
        2. 定义目标函数（训练模型并在验证集上评估）
        3. 使用 hyperopt.fmin() 执行优化
        4. 返回最优参数字典
        
        示例：
            from hyperopt import fmin, tpe, hp, Trials
            
            def objective(params):
                model = self.__class__(**params)
                model.fit(train_data)
                metrics = model.evaluate(val_data, prefix="val")
                return metrics["val_loss"]  # 最小化目标
            
            space = {
                'param1': hp.choice('param1', [10, 20, 30]),
                'param2': hp.uniform('param2', 0.1, 1.0)
            }
            
            best = fmin(objective, space, algo=tpe.suggest, max_evals=max_evals)
            return best
        """
        pass
    
    def get_params(self) -> Dict[str, Any]:
        """获取模型参数"""
        return self.config.copy()
    
    def _check_fitted(self):
        """检查模型是否已训练"""
        if not self.is_fitted:
            raise RuntimeError(f"{self.__class__.__name__} 必须先调用 fit()")


class ModelRegistry:
    """模型注册机制 - 支持动态模型加载
    
    使用方式：
        @ModelRegistry.register("my_model")
        class MyModel(Base{Domain}Model):
            ...
        
        # 动态创建模型
        model_class = ModelRegistry.get("my_model")
        model = model_class(**params)
    """
    
    _registry: Dict[str, Type[Base{Domain}Model]] = {}
    
    @classmethod
    def register(cls, name: str):
        """注册模型装饰器"""
        def decorator(model_class: Type[Base{Domain}Model]):
            if name in cls._registry:
                logger.warning(f"模型 '{name}' 已存在，将被覆盖")
            cls._registry[name] = model_class
            logger.info(f"模型已注册: {name} -> {model_class.__name__}")
            return model_class
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Type[Base{Domain}Model]:
        """获取注册的模型类"""
        if name not in cls._registry:
            available = ', '.join(cls._registry.keys())
            raise ValueError(
                f"未找到模型 '{name}'。可用模型: {available}"
            )
        return cls._registry[name]
    
    @classmethod
    def list_models(cls) -> list:
        """列出所有已注册的模型"""
        return list(cls._registry.keys())
```

### 具体模型实现示例

#### 模型类必须实现的方法

- `fit()`: 模型训练（必须）
- `predict()`: 预测逻辑（必须）
- `evaluate()`: 评估指标计算，注意使用 `prefix` 参数（必须）
- `optimize_hyperparams()`: 超参数优化（必须）
- `to_dict()`: 模型状态序列化（可选，简单模型可直接保存sklearn对象）
- `from_dict()`: 从字典恢复模型（可选，与to_dict配对使用）

#### MLflow 推理包装器（Wrapper）

**定义**：Wrapper 是继承自 `mlflow.pyfunc.PythonModel` 的类，用于将训练好的模型封装为 MLflow 可部署的推理接口。

**作用**：
1. **统一推理接口**：实现 `predict()` 方法，处理输入解析和输出格式化
2. **封装推理逻辑**：包含特征工程、数据预处理、后处理等完整推理流程
3. **支持模型持久化**：通过 `mlflow.pyfunc.save_model()` 保存为 MLflow 格式
4. **避免重型依赖**：推理时不需要导入训练相关的依赖（如 hyperopt）

**何时需要实现 Wrapper**：
- ✅ 模型推理需要额外的预处理或后处理逻辑
- ✅ 需要在推理时动态使用特征工程器
- ✅ 推理逻辑与训练逻辑差异较大（如递归预测、在线学习）
- ✅ 需要支持多种推理模式（如批量预测、流式预测）
- ❌ 简单的 sklearn 模型可直接使用 `mlflow.sklearn.log_model()`

**实现位置**：`training/models/{algorithm}_wrapper.py`

**标准结构**：
```python
import mlflow
import pandas as pd
import numpy as np

class {Algorithm}Wrapper(mlflow.pyfunc.PythonModel):
    """模型推理包装器"""
    
    def __init__(self, model, feature_engineer=None, **config):
        """初始化
        
        Args:
            model: 训练好的模型对象
            feature_engineer: 特征工程器（如需要）
            **config: 其他配置参数
        """
        self.model = model
        self.feature_engineer = feature_engineer
        self.config = config
    
    def predict(self, context, model_input):
        """推理接口
        
        Args:
            context: MLflow context（通常不使用）
            model_input: 输入数据（dict、DataFrame等）
            
        Returns:
            预测结果（numpy array、list等）
        """
        # 1. 解析输入
        X = self._parse_input(model_input)
        
        # 2. 特征工程（如需要）
        if self.feature_engineer:
            X = self.feature_engineer.transform(X)
        
        # 3. 模型预测
        predictions = self.model.predict(X)
        
        # 4. 后处理（如需要）
        return self._postprocess(predictions)
    
    def _parse_input(self, model_input):
        """解析输入数据（子类实现）"""
        raise NotImplementedError
    
    def _postprocess(self, predictions):
        """后处理预测结果（可选）"""
        return predictions
```

**与模型类的关系**：
```python
# 在模型类中创建 Wrapper 并保存到 MLflow
class MyModel(BaseModel):
    def save_to_mlflow(self, run_id: str):
        """保存模型到 MLflow"""
        # 创建 Wrapper
        wrapper = MyModelWrapper(
            model=self.model,
            feature_engineer=self.feature_engineer,
            config=self.config
        )
        
        # 保存为 MLflow pyfunc 格式
        mlflow.pyfunc.save_model(
            path=f"models/{run_id}",
            python_model=wrapper,
            artifacts={"model": self.model},
            conda_env=self._get_conda_env()
        )
```

**参考实现**：
- `classify_timeseries_server/training/models/gradient_boosting_wrapper.py`
- `classify_timeseries_server/training/models/prophet_wrapper.py`

详细实现请参考现有项目的具体模型文件。

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

**必需的顶层字段**：
1. `model`: 模型配置（type, name）
2. `hyperparams`: 超参数配置（含搜索空间）
3. `preprocessing`: 数据预处理配置
4. `feature_engineering`: 特征工程配置（必选）
5. `mlflow`: MLflow 实验跟踪配置（可选，使用环境变量）

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
    "search_space": {
      ...
    }
  },
  
  "feature_engineering": {
    ...
  },
  
  "preprocessing": {
    ...
  },
  "mlflow": {
    "experiment_name": "..."
  }
}
```

---

## 🔧 CLI 设计

### bootstrap.py 标准实现

```python
"""命令行接口 - 标准实现"""

from dotenv import load_dotenv
import fire
from loguru import logger
from pathlib import Path
import json

load_dotenv()


class CLI:
    """命令行工具"""
    
    def train(
        self,
        dataset_path: str,
        config: str,
        run_name: str = None,
    ):
        """训练模型
        
        Args:
            dataset_path: 数据集路径（目录或文件）
            config: 配置文件路径（必需）
            run_name: MLflow run 名称（可选）
        
        Environment Variables:
            MLFLOW_TRACKING_URI: MLflow 服务地址（必需）
        
        Example:
            # 基本训练
            export MLFLOW_TRACKING_URI=http://mlflow:5000
            classify_{domain}_server train \\
                --dataset-path ./data/ \\
                --config train.json
            
            # 自定义run名称
            classify_{domain}_server train \\
                --dataset-path ./data/ \\
                --config custom-train.json \\
                --run-name my_experiment_v1
        """
        from ..training import UniversalTrainer, TrainingConfig
        import os
        
        try:
            # 检查必需的环境变量
            if not os.getenv("MLFLOW_TRACKING_URI"):
                logger.error("❌ MLFLOW_TRACKING_URI 环境变量未设置")
                return
            
            # 检查配置文件是否存在
            config_path = Path(config)
            if not config_path.exists():
                logger.error(f"❌ 配置文件不存在: {config}")
                return
            
            # 加载配置
            config_obj = TrainingConfig.from_file(config)
            
            # 覆盖 run_name（如果提供）
            if run_name:
                config_obj.mlflow_run_name = run_name
            
            # 创建训练器并训练
            trainer = UniversalTrainer(config_obj)
            result = trainer.train(dataset_path)
            
            logger.info("✅ 训练成功完成")
            logger.info(f"Run ID: {result['run_id']}")
            
        except Exception as e:
            logger.error(f"❌ 训练失败: {e}", exc_info=True)
            raise
    
    def version(self):
        """显示版本信息"""
        print("classify_{domain}_server v0.1.0")


def main():
    """CLI 入口"""
    fire.Fire(CLI)


if __name__ == "__main__":
    main()
```

---

## 🐳 Docker 部署配置

### Dockerfile 标准实现

所有三个服务使用统一的 Dockerfile 结构，确保构建一致性：

```dockerfile
FROM python:3.12
WORKDIR /apps
ARG NEXUS_PYTHON_REPOSITY

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update -y
RUN apt-get install -y vim supervisor unzip curl fonts-wqy-zenhei

# 更新系统字体缓存
RUN fc-cache -fv

# 配置 pip 镜像源（如果提供）
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

# 安装 uv (Python 包管理工具)
RUN pip3 install uv

ADD . .

# 设置脚本和 mc 可执行权限
RUN chmod +x ./support-files/release/startup.sh && \
    chmod +x ./support-files/scripts/train-model.sh && \
    chmod +x ./mc

# 使用 uv 安装项目依赖并预先同步虚拟环境（通过命令行参数指定镜像源）
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    uv pip install --system --index-url "$NEXUS_PYTHON_REPOSITY" -e ".[dev]" && \
    uv sync --index-url "$NEXUS_PYTHON_REPOSITY"; \
    else \
    uv pip install --system -e ".[dev]" && \
    uv sync; \
    fi

# 清理 matplotlib 字体缓存，让其重新扫描字体
RUN rm -rf /root/.cache/matplotlib /root/.cache/fontconfig

RUN apt-get reinstall -y supervisor 

ENTRYPOINT ["/bin/bash","/apps/support-files/release/startup.sh"]
```

---

## 📜 训练脚本标准实现

### train-model.sh 核心要点

位置：`support-files/scripts/train-model.sh`

**核心功能**：
1. 从 MinIO 下载数据集（ZIP格式）
2. 解压到本地目录
3. 下载或使用本地配置文件 (未接收到传入配置文件路径则使用默认配置地址 默认存放位置 ./train.json(本地路径，和train-model.sh同一目录))
4. 调用 CLI 训练命令
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

