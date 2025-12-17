#!/bin/bash
# 时间序列模型训练脚本
# 功能：从 MinIO 下载训练数据集和配置文件，解压并训练时间序列模型，结果记录到 MLflow
# 
# 用法1 (位置参数): ./train-model.sh [BUCKET_NAME] [DATASET_NAME] [CONFIG_NAME]
# 示例: ./train-model.sh my-bucket timeseries_data.zip train.json
#
# 用法2 (JSON参数): ./train-model.sh '{"MINIO_BUCKET":"...","DATASET_NAME":"...","CONFIG_NAME":"..."}'
# 示例: ./train-model.sh '{"MINIO_BUCKET":"my-bucket","DATASET_NAME":"data.zip","CONFIG_NAME":"train.json"}'
# exec > >(tee log_file.txt) 2>&1
# set -x
set -e  # 遇到错误立即退出

# ==================== 配置参数 ====================
MINIO_ALIAS="${MINIO_ALIAS:-myminio}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-${SCRIPT_DIR}/data/downloads}"
EXTRACT_DIR="${EXTRACT_DIR:-${SCRIPT_DIR}/data/datasets}"
CONFIG_DIR="${CONFIG_DIR:-${SCRIPT_DIR}/data/configs}"

# ==================== 参数解析（支持JSON和位置参数） ====================
# 检测第一个参数是否为 JSON 格式
if [[ "$1" =~ ^\{.*\}$ ]]; then
    # JSON 参数模式
    log_info "检测到 JSON 参数格式"
    JSON_INPUT="$1"
    
    # 从 JSON 中提取参数（如果不存在则使用环境变量或默认值）
    MINIO_BUCKET=$(echo "${JSON_INPUT}" | jq -r '.minio_bucket // empty')
    DATASET_NAME=$(echo "${JSON_INPUT}" | jq -r '.dataset_name // empty')
    CONFIG_NAME=$(echo "${JSON_INPUT}" | jq -r '.config_name // empty')
    
    # 应用默认值（如果 JSON 中未提供）
    MINIO_BUCKET="${MINIO_BUCKET:-${MINIO_BUCKET:-datasets}}"
    DATASET_NAME="${DATASET_NAME:-${DATASET_NAME:-timeseries_train_data.zip}}"
    # CONFIG_NAME 保持为空或 JSON 提供的值
else
    # 传统位置参数模式
    MINIO_BUCKET="${1:-${MINIO_BUCKET:-datasets}}"
    DATASET_NAME="${2:-${DATASET_NAME:-timeseries_train_data.zip}}"
    CONFIG_NAME="$3"
fi

# MLflow 配置
MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://127.0.0.1:15000}"

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
log_info "检查必要的命令是否存在..."
check_command mc
check_command uv
check_command unzip
check_command jq

# 检查 mc 别名是否配置
if ! mc alias list | grep -q "^${MINIO_ALIAS}"; then
    log_error "MinIO 别名 '${MINIO_ALIAS}' 未配置"
    log_error "请先运行: mc alias set ${MINIO_ALIAS} http://your-minio-server:9000 ACCESS_KEY SECRET_KEY"
    exit 1
fi

# ==================== 创建目录 ====================
log_info "创建必要的目录..."
mkdir -p "${DOWNLOAD_DIR}"
mkdir -p "${EXTRACT_DIR}"
mkdir -p "${CONFIG_DIR}"

# ==================== 下载数据集 ====================
log_info "从 MinIO 下载数据集: ${MINIO_BUCKET}/${DATASET_NAME}"
DATASET_FILE="${DOWNLOAD_DIR}/$(basename ${DATASET_NAME})"

if mc cp "${MINIO_ALIAS}/${MINIO_BUCKET}/${DATASET_NAME}" "${DATASET_FILE}"; then
    log_info "数据集下载成功: ${DATASET_FILE}"
else
    log_error "数据集下载失败"
    exit 1
fi

# ==================== 解压数据集 ====================
log_info "解压数据集到: ${EXTRACT_DIR}"
if unzip -o "${DATASET_FILE}" -d "${EXTRACT_DIR}"; then
    log_info "数据集解压成功"
else
    log_error "数据集解压失败"
    exit 1
fi

# ==================== 准备配置文件 ====================
if [ -n "$3" ]; then
    # 用户指定了配置名称，从 MinIO 下载
    log_info "从 MinIO 下载配置文件: ${MINIO_BUCKET}/${CONFIG_NAME}"
    CONFIG_FILE="${CONFIG_DIR}/$(basename ${CONFIG_NAME})"
    
    if mc cp "${MINIO_ALIAS}/${MINIO_BUCKET}/${CONFIG_NAME}" "${CONFIG_FILE}" 2>/dev/null; then
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
log_info "开始训练时间序列模型..."
log_info "数据集目录: ${EXTRACT_DIR}"
log_info "配置文件: ${CONFIG_FILE}"
log_info "MLflow Tracking URI: ${MLFLOW_TRACKING_URI}"

export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI}"

# 构建训练命令
TRAIN_CMD="uv run classify_timeseries_server train \
    --dataset-path \"${EXTRACT_DIR}\" \
    --config \"${CONFIG_FILE}\""

# 执行训练
if eval ${TRAIN_CMD}; then
    log_info "模型训练成功！"
    log_info "详细信息请查看 MLflow UI"
else
    log_error "模型训练失败"
    exit 1
fi

# ==================== 清理（可选） ====================
if [ "${CLEANUP_AFTER_TRAIN:-false}" = "true" ]; then
    log_info "清理下载的压缩包..."
    rm -f "${DATASET_FILE}"
fi

