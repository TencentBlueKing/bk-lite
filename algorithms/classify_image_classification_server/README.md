# 图片分类服务 (Image Classification Server)

基于YOLO 11的图片分类微服务，提供高性能的批量预测API。

## 特性

- ✅ **批量预测优化**：充分利用YOLO批处理能力，GPU吞吐量提升4-7倍
- ✅ **统一接口设计**：与其他算法服务（timeseries/anomaly）架构一致
- ✅ **详细元数据**：提供分阶段耗时、成功率等丰富统计信息
- ✅ **部分失败处理**：批量请求中单张图片失败不影响其他图片
- ✅ **多格式支持**：兼容纯base64和Data URI格式
- ✅ **可观测性**：集成Prometheus指标和详细日志

## 快速开始

### 安装

```bash
# 安装依赖
pip install -e .

# 或使用poetry
poetry install
```

### 启动服务

```bash
# 开发模式
bentoml serve classify_image_classification_server.serving.service:MLService

# 生产模式
bentoml serve classify_image_classification_server.serving.service:MLService --production
```

### 配置

通过环境变量配置模型来源：

```bash
# 本地模型
export MODEL_SOURCE=local
export MODEL_PATH=/path/to/mlflow/model

# MLflow Registry
export MODEL_SOURCE=mlflow
export MLFLOW_MODEL_URI=models:/model_name/Production

# Dummy模型（测试）
export MODEL_SOURCE=dummy
```

## API 使用

### 预测接口

**端点**: `POST /predict`

**请求格式**:
```json
{
    "images": [
        "iVBORw0KGgo...",  // 纯base64
        "data:image/jpeg;base64,/9j/4AAQ..."  // Data URI
    ],
    "top_k": 5  // 可选，默认5
}
```

**响应格式**:
```json
{
    "results": [
        {
            "predictions": [
                {"class_id": 0, "class_name": "cat", "confidence": 0.95},
                {"class_id": 1, "class_name": "dog", "confidence": 0.03}
            ],
            "success": true,
            "error": null,
            "decode_time_ms": 15.2
        }
    ],
    "metadata": {
        "model_version": "yolo11n-cls.pt",
        "source": "local",
        "batch_size": 1,
        "total_time_ms": 45.3,
        "success_rate": 1.0
    },
    "success": true
}
```

### Python示例

**单张预测**:
```python
import requests
import base64

# 读取图片
with open("image.jpg", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

# 调用API
response = requests.post(
    "http://localhost:3000/predict",
    json={"images": [img_b64], "top_k": 5}
)

result = response.json()["results"][0]
if result["success"]:
    top_class = result["predictions"][0]
    print(f"{top_class['class_name']}: {top_class['confidence']:.2%}")
```

**批量预测**:
```python
import requests
import base64
from pathlib import Path

# 读取多张图片
images = []
for img_path in Path("images/").glob("*.jpg"):
    with open(img_path, "rb") as f:
        images.append(base64.b64encode(f.read()).decode())

# 批量调用
response = requests.post(
    "http://localhost:3000/predict",
    json={"images": images, "top_k": 3}
)

# 处理结果
for idx, result in enumerate(response.json()["results"]):
    if result["success"]:
        top_class = result["predictions"][0]
        print(f"Image {idx}: {top_class['class_name']} ({top_class['confidence']:.2%})")
    else:
        print(f"Image {idx} failed: {result['error']}")
```

## 迁移指南

从v1.x迁移到v2.0？请查看 [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)

## License

MIT
