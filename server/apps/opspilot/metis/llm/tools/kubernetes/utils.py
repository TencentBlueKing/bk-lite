"""Kubernetes工具的通用辅助函数"""

import base64
import io
import os

import yaml
from kubernetes import config

from apps.core.logger import opspilot_logger as logger


def _resolve_file_to_inline_data(obj, file_key, data_key, base64_encode=True):
    """将 kubeconfig 中的文件路径引用转换为 inline data 字段。

    Args:
        obj: kubeconfig 中的 cluster 或 user 字典
        file_key: 文件路径字段名，如 'certificate-authority'
        data_key: inline data 字段名，如 'certificate-authority-data'
        base64_encode: 是否对文件内容进行 base64 编码
    """
    if not obj or file_key not in obj:
        return
    if data_key in obj:
        # inline data 已存在，优先使用，删除文件路径引用
        del obj[file_key]
        return

    file_path = obj[file_key]
    if not os.path.isfile(file_path):
        logger.warning("kubeconfig 引用的文件不存在: %s", file_path)
        raise ValueError(f"kubeconfig 中 {file_key} 引用的文件不存在或服务端无法访问: " f"{file_path}。请将文件内容直接内联到 kubeconfig 中" "（使用 *-data 字段），或确保服务端可以访问该路径。")

    try:
        if base64_encode:
            with open(file_path, "rb") as f:
                obj[data_key] = base64.standard_b64encode(f.read()).decode("utf-8")
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                obj[data_key] = f.read().strip()
        del obj[file_key]
    except Exception as e:
        logger.warning("读取 kubeconfig 引用文件 %s 失败: %s", file_path, e)


def _represent_str_no_fold(dumper, data):
    """强制长字符串使用双引号，避免 token 被折叠。"""
    if "\n" in data or len(data) > 80:
        return dumper.represent_scalar(
            "tag:yaml.org,2002:str",
            data,
            style='"',
        )
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _preprocess_kubeconfig(kubeconfig_data):
    """预处理 kubeconfig YAML，将文件路径引用转换为 inline data。

    处理字段：
    - clusters[].cluster.certificate-authority -> certificate-authority-data
    - users[].user.client-certificate -> client-certificate-data
    - users[].user.client-key -> client-key-data
    - users[].user.tokenFile → token (明文，strip 换行)

    Args:
        kubeconfig_data: kubeconfig YAML 字符串

    Returns:
        str: 预处理后的 kubeconfig YAML 字符串
    """
    try:
        kube_cfg = yaml.safe_load(kubeconfig_data)
    except yaml.YAMLError as e:
        logger.warning("kubeconfig YAML 解析失败，跳过预处理: %s", e)
        return kubeconfig_data

    if not isinstance(kube_cfg, dict):
        return kubeconfig_data

    # 处理 clusters
    for cluster_entry in kube_cfg.get("clusters", []) or []:
        cluster = cluster_entry.get("cluster", {})
        if cluster:
            _resolve_file_to_inline_data(
                cluster,
                "certificate-authority",
                "certificate-authority-data",
                base64_encode=True,
            )

    # 处理 users
    for user_entry in kube_cfg.get("users", []) or []:
        user = user_entry.get("user", {})
        if not user:
            continue
        # client 证书
        _resolve_file_to_inline_data(
            user,
            "client-certificate",
            "client-certificate-data",
            base64_encode=True,
        )
        _resolve_file_to_inline_data(
            user,
            "client-key",
            "client-key-data",
            base64_encode=True,
        )
        # tokenFile → token (明文，不做 base64)
        _resolve_file_to_inline_data(
            user,
            "tokenFile",
            "token",
            base64_encode=False,
        )
        # 对已有的 token 字段做 strip，去除多余空格和换行
        if "token" in user and isinstance(user["token"], str):
            user["token"] = user["token"].strip()

    dumper = yaml.Dumper
    dumper.add_representer(str, _represent_str_no_fold)
    return yaml.dump(
        kube_cfg,
        Dumper=dumper,
        default_flow_style=False,
        allow_unicode=True,
    )


def prepare_context(cfg):
    """
    准备Kubernetes客户端上下文

    Args:
        cfg: RunnableConfig配置对象
    """
    try:
        configurable = cfg.get("configurable", {}) if cfg else {}

        # Multi-instance path
        if configurable.get("kubernetes_instances"):
            from apps.opspilot.metis.llm.tools.kubernetes.connection import get_kubernetes_instances_from_configurable, resolve_kubernetes_instance

            instances = get_kubernetes_instances_from_configurable(configurable)
            if instances:
                instance = resolve_kubernetes_instance(
                    instances,
                    instance_name=configurable.get("instance_name"),
                    instance_id=configurable.get("instance_id"),
                )
                kubeconfig_data = instance.get("kubeconfig_data", "")
                if kubeconfig_data:
                    if isinstance(kubeconfig_data, str):
                        kubeconfig_data = kubeconfig_data.replace("\\n", "\n")
                    kubeconfig_data = _preprocess_kubeconfig(kubeconfig_data)
                    kubeconfig_io = io.StringIO(kubeconfig_data)
                    config.load_kube_config(config_file=kubeconfig_io)
                    return
                # No kubeconfig_data in instance — fall through to defaults

        # Legacy single-instance path
        if configurable.get("kubeconfig_data"):
            # 使用传入的 kubeconfig 配置内容
            kubeconfig_data = configurable["kubeconfig_data"]
            # 处理可能的转义换行符
            if isinstance(kubeconfig_data, str):
                kubeconfig_data = kubeconfig_data.replace("\\n", "\n")
            # 预处理：将文件路径引用转换为 inline data
            kubeconfig_data = _preprocess_kubeconfig(kubeconfig_data)
            # 将配置内容写入 IO 对象
            kubeconfig_io = io.StringIO(kubeconfig_data)
            config.load_kube_config(config_file=kubeconfig_io)
        else:
            # 首先尝试默认的 kubeconfig 路径 (~/.kube/config)
            try:
                config.load_kube_config()
            except Exception:
                # 如果默认路径失败，尝试集群内配置
                config.load_incluster_config()
    except Exception as e:
        logger.exception(e)
        raise Exception(f"无法加载 Kubernetes 配置: {str(e)}. " "请检查 kubeconfig 配置内容或集群连接。")


def format_bytes(size):
    """
    Format bytes to human readable string.

    Converts a byte value to a human-readable string with appropriate
    units (B, KiB, MiB, GiB, TiB).

    Args:
        size (int): Size in bytes

    Returns:
        str: Human-readable string representation of the size
            (e.g., "2.5 MiB")
    """
    power = 2**10
    n = 0
    power_labels = {0: "B", 1: "KiB", 2: "MiB", 3: "GiB", 4: "TiB"}
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {power_labels[n]}"


def parse_resource_quantity(quantity_str):
    """
    解析Kubernetes资源数量字符串为数值

    Args:
        quantity_str (str): 如 "100m", "1Gi", "500Mi" 等

    Returns:
        float: 转换后的数值
    """
    if not quantity_str:
        return 0

    # CPU资源 (cores)
    if quantity_str.endswith("m"):
        return float(quantity_str[:-1]) / 1000

    # 内存资源 (bytes)
    multipliers = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }

    for suffix, multiplier in multipliers.items():
        if quantity_str.endswith(suffix):
            return float(quantity_str[: -len(suffix)]) * multiplier

    # 无单位，直接转换
    try:
        return float(quantity_str)
    except ValueError:
        return 0
