#!/bin/bash
# 时间序列 SARIMA 模型训练脚本
# 功能：从 MinIO 下载训练数据集，解压并训练 SARIMA 模型，结果记录到 MLflow
# 
# 用法: ./train-model.sh [BUCKET_NAME] [DATASET_NAME]
# 示例: ./train-model.sh my-bucket timeseries_data.zip
# exec > >(tee log_file.txt) 2>&1
# set -x
set -e  # 遇到错误立即退出

# ==================== 配置参数 ====================
MINIO_ALIAS="${MINIO_ALIAS:-myminio}"
MINIO_BUCKET="${1:-${MINIO_BUCKET:-datasets}}"
DATASET_NAME="${2:-${DATASET_NAME:-timeseries_train_data.zip}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-${SCRIPT_DIR}/data/downloads}"
EXTRACT_DIR="${EXTRACT_DIR:-${SCRIPT_DIR}/data/datasets}"
CONFIG_FILE="${CONFIG_FILE:-${SCRIPT_DIR}/train.json}"

# 训练配置
ALGORITHM="${ALGORITHM:-sarima}"  # 模型算法: sarima, gradient_boosting, prophet, xgboost, lstm

# MLflow 配置
MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://127.0.0.1:15000}"
MLFLOW_EXPERIMENT_NAME="${MLFLOW_EXPERIMENT_NAME:-timeseries_${ALGORITHM}_test}"
MODEL_NAME="${MODEL_NAME:-timeseries_${ALGORITHM}_model}"

# 超参数优化配置
MAX_EVALS="${3:-${MAX_EVALS:-50}}"  # 0 = 不优化，>0 = 优化轮次
OPTIMIZATION_METRIC="${OPTIMIZATION_METRIC:-rmse}"  # 优化目标指标

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

# ==================== 准备训练配置文件 ====================
if [ ! -f "${CONFIG_FILE}" ]; then
    log_error "配置文件不存在: ${CONFIG_FILE}"
    log_error "请确保 train.json 文件存在"
    exit 1
fi

log_info "使用配置文件: ${CONFIG_FILE}"

# ==================== 训练模型 ====================
log_info "开始训练时间序列模型..."
log_info "模型算法: ${ALGORITHM}"
log_info "数据集目录: ${EXTRACT_DIR}"
log_info "  - 训练集: ${EXTRACT_DIR}/train_data.csv"
log_info "  - 验证集: ${EXTRACT_DIR}/val_data.csv"
log_info "  - 测试集: ${EXTRACT_DIR}/test_data.csv"
log_info "配置文件: ${CONFIG_FILE}"
log_info "MLflow Tracking URI: ${MLFLOW_TRACKING_URI}"
log_info "MLflow Experiment: ${MLFLOW_EXPERIMENT_NAME}"
log_info "模型名称: ${MODEL_NAME}"
log_info "超参数优化轮次: ${MAX_EVALS}"
if [ "${MAX_EVALS}" -gt 0 ]; then
    log_info "优化目标指标: ${OPTIMIZATION_METRIC}"
fi

# 检查数据文件是否存在
TRAIN_DATA="${EXTRACT_DIR}/train_data.csv"
VAL_DATA="${EXTRACT_DIR}/val_data.csv"
TEST_DATA="${EXTRACT_DIR}/test_data.csv"

if [ ! -f "${TRAIN_DATA}" ]; then
    log_error "训练数据文件不存在: ${TRAIN_DATA}"
    exit 1
fi

export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI}"

# 构建训练命令
TRAIN_CMD="uv run classify_timeseries_server train \
    --dataset-path \"${TRAIN_DATA}\" \
    --config \"${CONFIG_FILE}\" \
    --algorithm \"${ALGORITHM}\" \
    --experiment-name \"${MLFLOW_EXPERIMENT_NAME}\" \
    --model-name \"${MODEL_NAME}\" \
    --test-size 0.2 \
    --max-evals ${MAX_EVALS} \
    --optimization-metric ${OPTIMIZATION_METRIC}"

# 添加验证集和测试集参数（如果文件存在）
if [ -f "${VAL_DATA}" ]; then
    TRAIN_CMD="${TRAIN_CMD} \
    --val-dataset-path \"${VAL_DATA}\""
    log_info "已添加验证集"
fi

if [ -f "${TEST_DATA}" ]; then
    TRAIN_CMD="${TRAIN_CMD} \
    --test-dataset-path \"${TEST_DATA}\""
    log_info "已添加测试集"
fi

# 执行训练
if eval ${TRAIN_CMD}; then
    log_info "模型训练成功！"
    log_info "模型已注册到 MLflow: ${MODEL_NAME}"
else
    log_error "模型训练失败"
    exit 1
fi

# ==================== 清理（可选） ====================
if [ "${CLEANUP_AFTER_TRAIN:-false}" = "true" ]; then
    log_info "清理下载的压缩包..."
    rm -f "${DATASET_FILE}"
fi

