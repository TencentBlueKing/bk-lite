"""配置schema定义."""

# 支持的模型类型
SUPPORTED_MODELS = ["YOLOClassification"]

# 支持的设备类型
SUPPORTED_DEVICES = ["auto", "cpu", "gpu", "gpus"]

# 支持的优化器
SUPPORTED_OPTIMIZERS = ["SGD", "Adam", "AdamW", "RMSprop", "auto"]
