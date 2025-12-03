"""Kubernetes工具的通用辅助函数"""
from kubernetes import client, config


def prepare_context(cfg):
    """
    准备Kubernetes客户端上下文

    Args:
        cfg: RunnableConfig配置对象
    """
    try:
        if cfg and cfg.get('configurable', {}).get('kubeconfig_path'):
            # 使用指定的 kubeconfig 路径
            config.load_kube_config(
                config_file=cfg['configurable']['kubeconfig_path'])
        else:
            # 首先尝试默认的 kubeconfig 路径 (~/.kube/config)
            try:
                config.load_kube_config()
            except Exception:
                # 如果默认路径失败，尝试集群内配置
                config.load_incluster_config()
    except Exception as e:
        raise Exception(
            f"无法加载 Kubernetes 配置: {str(e)}. 请检查 kubeconfig 文件路径或集群连接。")


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
    power = 2 ** 10
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
    if quantity_str.endswith('m'):
        return float(quantity_str[:-1]) / 1000

    # 内存资源 (bytes)
    multipliers = {
        'Ki': 1024,
        'Mi': 1024**2,
        'Gi': 1024**3,
        'Ti': 1024**4,
        'K': 1000,
        'M': 1000**2,
        'G': 1000**3,
        'T': 1000**4
    }

    for suffix, multiplier in multipliers.items():
        if quantity_str.endswith(suffix):
            return float(quantity_str[:-len(suffix)]) * multiplier

    # 无单位，直接转换
    try:
        return float(quantity_str)
    except ValueError:
        return 0
