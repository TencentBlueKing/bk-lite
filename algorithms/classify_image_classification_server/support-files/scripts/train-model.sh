#!/bin/bash
# 图片分类模型训练脚本
# 功能：从 MinIO 下载训练数据集和配置文件，解压并训练YOLO图片分类模型，结果记录到 MLflow
# 
# 用法: ./train-model.sh [BUCKET] [DATASET] [CONFIG]
# 示例: ./train-model.sh datasets image_classification_data.zip configs/train.json
# 
# 参数说明：
#   BUCKET   - MinIO bucket 名称 (默认: datasets)
#   DATASET  - 数据集文件路径 (默认: image_classification_train_data.zip)
#   CONFIG   - 配置文件路径 (可选，默认使用本地 train.json)
# 
# 数据集格式要求：
#   ZIP 包解压后应为 ImageFolder 格式：
#   dataset/
#     ├── train/
#     │   ├── class1/
#     │   │   ├── img1.jpg
#     │   │   └── img2.jpg
#     │   └── class2/
#     │       └── img3.jpg
#     ├── val/
#     └── test/
# 
# exec > >(tee log_file.txt) 2>&1
# set -x
set -e  # 遇到错误立即退出

# ==================== 配置参数 ====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# MLflow 配置
MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://10.10.41.149:15000}"

# MinIO 参数
MC_BIN="${MC_BIN:-${PROJECT_ROOT}/mc}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-${SCRIPT_DIR}/data/downloads}"
EXTRACT_DIR="${EXTRACT_DIR:-${SCRIPT_DIR}/data/datasets}"
CONFIG_DIR="${CONFIG_DIR:-${SCRIPT_DIR}/data/configs}"

# MinIO 连接配置（通过环境变量配置）
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://10.10.41.149:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minio}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-x6dES11CBh2omEuuujMK96Q0GWHrSCQ6}"

# 参数解析
MINIO_BUCKET="${1:-${MINIO_BUCKET:-datasets}}"
DATASET_NAME="${2:-${DATASET_NAME:-image_classification_train_data.zip}}"
CONFIG_NAME="$3"

# ==================== 函数定义 ====================
function log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

function log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

function check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "$1 未安装，请先安装"
        exit 1
    fi
}

# ==================== 环境检查 ====================
log_info "检查必要的命令和文件是否存在..."

check_command uv
check_command python
check_command unzip

# 检查 mc 二进制文件
if [ ! -f "${MC_BIN}" ]; then
    log_error "MinIO Client 二进制文件不存在: ${MC_BIN}"
    log_error "请确保 mc 二进制文件已放置在项目根目录"
    exit 1
fi

if [ ! -x "${MC_BIN}" ]; then
    log_error "MinIO Client 二进制文件不可执行: ${MC_BIN}"
    log_error "请运行: chmod +x ${MC_BIN}"
    exit 1
fi

log_info "使用 MinIO Client: ${MC_BIN}"

# 检查 MinIO 连接配置
if [ -z "${MINIO_ENDPOINT}" ] || [ -z "${MINIO_ACCESS_KEY}" ] || [ -z "${MINIO_SECRET_KEY}" ]; then
    log_error "MinIO 连接信息未配置"
    log_error "请设置以下环境变量："
    log_error "  MINIO_ENDPOINT=http://your-minio-server:9000"
    log_error "  MINIO_ACCESS_KEY=your-access-key"
    log_error "  MINIO_SECRET_KEY=your-secret-key"
    exit 1
fi

log_info "MinIO Endpoint: ${MINIO_ENDPOINT}"

# ==================== MinIO 下载数据 ====================

# 创建目录
log_info "创建必要的目录..."
mkdir -p "${DOWNLOAD_DIR}"
mkdir -p "${CONFIG_DIR}"

# 清理旧的数据集目录（避免不同训练任务的数据混淆）
if [ -d "${EXTRACT_DIR}" ]; then
    log_info "清理旧数据集目录: ${EXTRACT_DIR}"
    rm -rf "${EXTRACT_DIR}"
fi
mkdir -p "${EXTRACT_DIR}"

# 下载数据集
log_info "从 MinIO 下载数据集: ${MINIO_BUCKET}/${DATASET_NAME}"
DATASET_FILE="${DOWNLOAD_DIR}/$(basename ${DATASET_NAME})"

# 配置 MinIO 连接
log_info "配置 MinIO 连接..."
if ! "${MC_BIN}" alias set minio "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" > /dev/null 2>&1; then
    log_error "无法连接到 MinIO: ${MINIO_ENDPOINT}"
    exit 1
fi

if "${MC_BIN}" cp "minio/${MINIO_BUCKET}/${DATASET_NAME}" "${DATASET_FILE}"; then
    log_info "数据集下载成功: ${DATASET_FILE}"
else
    log_error "数据集下载失败"
    exit 1
fi

# 解压数据集
log_info "解压数据集到: ${EXTRACT_DIR}"
if unzip -o "${DATASET_FILE}" -d "${EXTRACT_DIR}"; then
    log_info "数据集解压成功"
else
    log_error "数据集解压失败"
    exit 1
fi

# 验证 ImageFolder 格式
log_info "验证数据集格式（ImageFolder）..."
DATASET_ROOT="${EXTRACT_DIR}"

# 查找实际数据集根目录（可能在子目录中）
if [ -d "${EXTRACT_DIR}/train" ]; then
    DATASET_ROOT="${EXTRACT_DIR}"
    log_info "数据集根目录: ${DATASET_ROOT}"
elif [ -d "${EXTRACT_DIR}/dataset" ]; then
    DATASET_ROOT="${EXTRACT_DIR}/dataset"
    log_info "数据集根目录: ${DATASET_ROOT}"
else
    # 查找第一个包含train目录的子目录
    for dir in "${EXTRACT_DIR}"/*; do
        if [ -d "${dir}/train" ]; then
            DATASET_ROOT="${dir}"
            log_info "数据集根目录: ${DATASET_ROOT}"
            break
        fi
    done
fi

if [ ! -d "${DATASET_ROOT}/train" ]; then
    log_error "数据集格式错误：未找到 train 目录"
    log_error "期望格式: dataset/train/class_name/*.jpg"
    exit 1
fi

log_info "✓ 数据集格式验证通过"

# 准备配置文件
if [ -n "$3" ]; then
    # 用户指定了配置名称，从 MinIO 下载
    log_info "从 MinIO 下载配置文件: ${MINIO_BUCKET}/${CONFIG_NAME}"
    CONFIG_FILE="${CONFIG_DIR}/$(basename ${CONFIG_NAME})"
    
    if "${MC_BIN}" cp "minio/${MINIO_BUCKET}/${CONFIG_NAME}" "${CONFIG_FILE}" 2>/dev/null; then
        log_info "配置文件下载成功: ${CONFIG_FILE}"
    else
        log_error "配置文件下载失败: ${MINIO_BUCKET}/${CONFIG_NAME}"
        log_error "请确保 MinIO 中存在该配置文件"
        exit 1
    fi
else
    # 用户未指定，使用脚本同目录的本地默认配置
    CONFIG_FILE="${SCRIPT_DIR}/train.json"
    
    if [ -f "${CONFIG_FILE}" ]; then
        log_info "使用本地默认配置: ${CONFIG_FILE}"
    else
        log_error "本地默认配置不存在: ${CONFIG_FILE}"
        log_error "请确保脚本目录下存在 train.json 文件"
        exit 1
    fi
fi

# ==================== 训练模型 ====================
log_info "开始训练YOLO图片分类模型..."
log_info "数据集目录: ${DATASET_ROOT}"
log_info "配置文件: ${CONFIG_FILE}"
log_info "MLflow Tracking URI: ${MLFLOW_TRACKING_URI}"

export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI}"

# 切换到项目根目录
cd "${PROJECT_ROOT}"

# 构建训练命令（使用注册的 CLI 命令）
TRAIN_CMD="uv run classify_image_classification_server train \
    --dataset-path=\"${DATASET_ROOT}\" \
    --config=\"${CONFIG_FILE}\""

# 执行训练
if eval ${TRAIN_CMD}; then
    log_info "模型训练成功！"
    log_info "详细信息请查看 MLflow UI: ${MLFLOW_TRACKING_URI}"
else
    log_error "模型训练失败"
    exit 1
fi

# ==================== 清理（可选） ====================
if [ "${CLEANUP_AFTER_TRAIN:-false}" = "true" ]; then
    log_info "清理下载的压缩包..."
    rm -f "${DATASET_FILE}"
fi

log_info "训练流程完成！"
