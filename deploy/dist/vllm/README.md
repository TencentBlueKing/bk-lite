# vLLM with ModelScope Models

## 概述

这个Dockerfile用于构建一个包含预下载模型的vLLM镜像,包括:

- **bce-embedding-base_v1**: BCE embedding模型
- **OlmOCR-7B-0725**: OCR大语言模型
- **bce-reranker-base_v1**: BCE rerank模型
- **FastEmbed**: 默认embedding模型

## 文件说明

- `Dockerfile`: Docker镜像构建文件
- `download_models.py`: 模型下载脚本

## 构建镜像

```bash
# 在当前目录下构建
docker build -t vllm-with-models:latest .
```

## 运行容器

```bash
# 基本运行
docker run -d \
  --name vllm-server \
  -p 8000:8000 \
  --gpus all \
  vllm-with-models:latest

# 自定义模型路径运行
docker run -d \
  --name vllm-server \
  -p 8000:8000 \
  --gpus all \
  -v /path/to/models:/root/.cache/modelscope/hub \
  vllm-with-models:latest
```

## 模型存储位置

- ModelScope模型: `/root/.cache/modelscope/hub`
- FastEmbed模型: `/root/.cache/fastembed`

## 自定义启动参数

如果需要使用特定模型启动vLLM,可以覆盖CMD:

```bash
docker run -d \
  --name vllm-server \
  -p 8000:8000 \
  --gpus all \
  vllm-with-models:latest \
  python -m vllm.entrypoints.openai.api_server \
  --model /root/.cache/modelscope/hub/maidalun/bce-embedding-base_v1 \
  --host 0.0.0.0 \
  --port 8000
```

## 注意事项

1. 构建过程中会下载模型,需要较长时间和足够的磁盘空间
2. 建议使用GPU运行,添加 `--gpus all` 参数
3. 模型文件较大,建议使用挂载卷持久化模型数据
