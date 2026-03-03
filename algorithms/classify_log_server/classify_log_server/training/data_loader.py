"""日志聚类训练的数据加载器"""

from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger


class LogDataLoader:
    """日志文件数据加载器
    
    支持从 TXT 文件加载日志（logpai 格式）。
    """

    def __init__(self, encoding: str = "utf-8"):
        """初始化数据加载器

        Args:
            encoding: 文件编码
        """
        self.encoding = encoding

    def load_txt(self, file_path: str) -> List[str]:
        """从 TXT 文件加载日志

        每一行被视为一条单独的日志消息。

        Args:
            file_path: TXT 文件路径

        Returns:
            日志消息列表
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Log file not found: {file_path}")

        logs = []
        with open(file_path, "r", encoding=self.encoding) as f:
            for line in f:
                line = line.strip()
                if line:  # 跳过空行
                    logs.append(line)

        logger.info(f"Loaded {len(logs)} logs from {file_path}")
        return logs

    def load_ground_truth(self, file_path: str) -> List[int]:
        """从文件加载真实标签

        每一行包含一个聚类 ID（整数）。

        Args:
            file_path: 真实标签文件路径

        Returns:
            聚类 ID 列表
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Ground truth file not found: {file_path}")

        labels = []
        with open(file_path, "r", encoding=self.encoding) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        label = int(line)
                        labels.append(label)
                    except ValueError:
                        logger.warning(f"Invalid label: {line}, skipping")

        logger.info(f"Loaded {len(labels)} ground truth labels from {file_path}")
        return labels

    def load_train_test_split(
        self,
        train_file: str,
        test_file: Optional[str] = None,
        train_gt_file: Optional[str] = None,
        test_gt_file: Optional[str] = None,
    ) -> Tuple[List[str], Optional[List[str]], Optional[List[int]], Optional[List[int]]]:
        """加载训练和测试数据

        Args:
            train_file: 训练日志文件路径
            test_file: 测试日志文件路径（可选）
            train_gt_file: 训练真实标签文件路径（可选）
            test_gt_file: 测试真实标签文件路径（可选）

        Returns:
            元组 (train_logs, test_logs, train_labels, test_labels)
        """
        # 加载训练数据
        train_logs = self.load_txt(train_file)
        train_labels = None
        if train_gt_file:
            train_labels = self.load_ground_truth(train_gt_file)
            if len(train_labels) != len(train_logs):
                raise ValueError(
                    f"Training labels ({len(train_labels)}) and logs ({len(train_logs)}) length mismatch"
                )

        # 加载测试数据
        test_logs = None
        test_labels = None
        if test_file:
            test_logs = self.load_txt(test_file)
            if test_gt_file:
                test_labels = self.load_ground_truth(test_gt_file)
                if len(test_labels) != len(test_logs):
                    raise ValueError(
                        f"Test labels ({len(test_labels)}) and logs ({len(test_logs)}) length mismatch"
                    )

        logger.info(
            f"Loaded train: {len(train_logs)} logs, test: {len(test_logs) if test_logs else 0} logs"
        )

        return train_logs, test_logs, train_labels, test_labels

    def save_logs(self, logs: List[str], output_path: str):
        """保存日志到 TXT 文件

        Args:
            logs: 日志消息列表
            output_path: 输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding=self.encoding) as f:
            for log in logs:
                f.write(log + "\n")

        logger.info(f"Saved {len(logs)} logs to {output_path}")

    def save_ground_truth(self, labels: List[int], output_path: str):
        """保存真实标签到文件

        Args:
            labels: 聚类 ID 列表
            output_path: 输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding=self.encoding) as f:
            for label in labels:
                f.write(str(label) + "\n")

        logger.info(f"Saved {len(labels)} labels to {output_path}")
