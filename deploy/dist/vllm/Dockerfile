# ============================================
# 阶段1: 模型下载阶段
# ============================================
FROM python:3.10-slim AS model-downloader

# 设置工作目录
WORKDIR /app

# 安装模型下载所需的依赖
RUN pip install --no-cache-dir modelscope -i https://repo.huaweicloud.com/repository/pypi/simple

# 设置模型存储目录
ENV MODEL_DIR=/models/modelscope

# 创建模型目录
RUN mkdir -p ${MODEL_DIR}

# 下载模型1: bce-embedding-base_v1
RUN python -c "from modelscope import snapshot_download; \
snapshot_download('maidalun/bce-embedding-base_v1', cache_dir='${MODEL_DIR}')"

# 下载模型2: OlmOCR-7B-0725
RUN python -c "from modelscope import snapshot_download; \
snapshot_download('allenai/OlmOCR-7B-0725', cache_dir='${MODEL_DIR}')"

# 下载模型3: bce-reranker-base_v1
RUN python -c "from modelscope import snapshot_download; \
snapshot_download('maidalun/bce-reranker-base_v1', cache_dir='${MODEL_DIR}')"

# 下载模型4: bge-large-zh-v1.5 (BGE embedding模型)
RUN python -c "from modelscope import snapshot_download; \
snapshot_download('AI-ModelScope/bge-large-zh-v1.5', cache_dir='${MODEL_DIR}')"

# ============================================
# 阶段2: 运行时阶段
# ============================================
FROM vllm/vllm-openai:latest

# 从构建阶段复制模型文件到vllm默认目录
COPY --from=model-downloader /models/modelscope /root/.cache/huggingface/hub

# 设置环境变量启用离线模式
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# 暴露vllm默认端口
EXPOSE 8000

# 启动命令(可根据实际需求调整)
# 使用环境变量 MODEL_NAME 来指定要启动的模型,默认为 bge-large-zh-v1.5
ENV MODEL_NAME=AI-ModelScope/bge-large-zh-v1.5
CMD python -m vllm.entrypoints.openai.api_server \
    --model ${MODEL_NAME} \
    --host 0.0.0.0 \
    --port 8000
