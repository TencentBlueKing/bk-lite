#!/usr/bin/env python3
"""
MinIO 数据集下载工具

功能：从 MinIO 下载训练数据集和配置文件
使用 MinIO 原生 Python SDK (minio-py)

用法：
    python download_dataset.py --bucket BUCKET --object-path PATH --output OUTPUT
    python download_dataset.py --bucket munchkin-public --object-path datasets/data.zip --output ./data.zip

环境变量：
    MINIO_ENDPOINT      - MinIO 服务地址 (默认: localhost:9000)
    MINIO_ACCESS_KEY    - MinIO 访问密钥
    MINIO_SECRET_KEY    - MinIO 密钥
    MINIO_USE_HTTPS     - 是否使用 HTTPS (0/1, 默认: 0)
"""

import os
import sys
from pathlib import Path
from typing import Optional

import fire
from loguru import logger
from minio import Minio
from minio.error import S3Error


class MinioDownloader:
    """MinIO 数据下载器"""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        use_https: Optional[bool] = None,
    ):
        """
        初始化 MinIO 客户端

        Args:
            endpoint: MinIO 服务地址 (host:port)
            access_key: 访问密钥
            secret_key: 密钥
            use_https: 是否使用 HTTPS
        """
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
        # 清理协议前缀 (MinIO SDK 不接受 http:// 或 https://)
        self.endpoint = self.endpoint.replace("http://", "").replace("https://", "")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY")

        # 处理 use_https: 支持字符串 "0"/"1" 和布尔值
        if use_https is None:
            use_https_env = os.getenv("MINIO_USE_HTTPS", "0")
            self.use_https = use_https_env in ("1", "true", "True", "yes")
        else:
            self.use_https = use_https

        if not self.access_key or not self.secret_key:
            logger.error("MinIO 认证信息未配置")
            logger.error("请设置环境变量: MINIO_ACCESS_KEY, MINIO_SECRET_KEY")
            sys.exit(1)

        logger.info(f"连接 MinIO: {self.endpoint} (HTTPS: {self.use_https})")

        try:
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.use_https,
            )
            logger.success("MinIO 客户端初始化成功")
        except Exception as e:
            logger.error(f"MinIO 客户端初始化失败: {e}")
            sys.exit(1)

    def download(
        self,
        bucket: str,
        object_path: str,
        output: str,
        create_dirs: bool = True,
    ) -> bool:
        """
        下载文件

        Args:
            bucket: 存储桶名称
            object_path: 对象路径
            output: 输出文件路径
            create_dirs: 是否自动创建目录

        Returns:
            下载是否成功
        """
        try:
            output_path = Path(output)

            # 创建输出目录
            if create_dirs:
                output_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"开始下载: {bucket}/{object_path}")
            logger.info(f"保存到: {output_path.absolute()}")

            # 下载文件
            self.client.fget_object(
                bucket_name=bucket,
                object_name=object_path,
                file_path=str(output_path),
            )

            file_size = output_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            logger.success(f"下载成功! 文件大小: {size_mb:.2f} MB")
            return True

        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.error(f"文件不存在: {bucket}/{object_path}")
            elif e.code == "NoSuchBucket":
                logger.error(f"存储桶不存在: {bucket}")
            else:
                logger.error(f"S3 错误: {e}")
            return False
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        recursive: bool = True,
    ) -> list[str]:
        """
        列出对象

        Args:
            bucket: 存储桶名称
            prefix: 对象前缀
            recursive: 是否递归列出

        Returns:
            对象名称列表
        """
        try:
            logger.info(f"列出对象: {bucket}/{prefix}")
            objects = self.client.list_objects(
                bucket_name=bucket,
                prefix=prefix,
                recursive=recursive,
            )
            object_names = [obj.object_name for obj in objects]
            logger.info(f"找到 {len(object_names)} 个对象")
            for name in object_names[:10]:  # 只显示前10个
                logger.info(f"  - {name}")
            if len(object_names) > 10:
                logger.info(f"  ... 还有 {len(object_names) - 10} 个对象")
            return object_names
        except Exception as e:
            logger.error(f"列出对象失败: {e}")
            return []

    def download_batch(
        self,
        bucket: str,
        object_paths: list[str],
        output_dir: str,
        keep_structure: bool = True,
    ) -> dict[str, bool]:
        """
        批量下载文件

        Args:
            bucket: 存储桶名称
            object_paths: 对象路径列表
            output_dir: 输出目录
            keep_structure: 是否保持目录结构

        Returns:
            下载结果字典 {object_path: success}
        """
        results = {}
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"批量下载 {len(object_paths)} 个文件到: {output_path.absolute()}")

        for object_path in object_paths:
            if keep_structure:
                # 保持原始目录结构
                local_path = output_path / object_path
            else:
                # 只保存文件名
                local_path = output_path / Path(object_path).name

            success = self.download(
                bucket=bucket,
                object_path=object_path,
                output=str(local_path),
                create_dirs=True,
            )
            results[object_path] = success

        success_count = sum(results.values())
        logger.info(f"批量下载完成: {success_count}/{len(object_paths)} 成功")
        return results


def main(
    bucket: Optional[str] = None,
    object_path: Optional[str] = None,
    output: Optional[str] = None,
    endpoint: Optional[str] = None,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    use_https: Optional[bool] = None,
    list_only: bool = False,
    prefix: str = "",
    batch_file: Optional[str] = None,
    output_dir: Optional[str] = None,
):
    """
    MinIO 数据集下载工具

    Args:
        bucket: 存储桶名称
        object_path: 对象路径 (单文件下载时使用)
        output: 输出文件路径 (单文件下载时使用)
        endpoint: MinIO 服务地址
        access_key: 访问密钥
        secret_key: 密钥
        use_https: 是否使用 HTTPS
        list_only: 仅列出对象，不下载
        prefix: 对象前缀 (列出对象时使用)
        batch_file: 批量下载文件列表 (每行一个对象路径)
        output_dir: 批量下载输出目录

    Examples:
        # 单文件下载
        python download_dataset.py --bucket my-bucket --object-path data.zip --output ./data.zip

        # 列出对象
        python download_dataset.py --bucket my-bucket --list-only --prefix datasets/

        # 批量下载
        python download_dataset.py --bucket my-bucket --batch-file files.txt --output-dir ./downloads
    """
    downloader = MinioDownloader(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        use_https=use_https,
    )

    # 模式1: 仅列出对象
    if list_only:
        if not bucket:
            logger.error("必须指定 --bucket")
            sys.exit(1)
        downloader.list_objects(bucket=bucket, prefix=prefix)
        return

    # 模式2: 批量下载
    if batch_file:
        if not bucket or not output_dir:
            logger.error("批量下载需要指定 --bucket 和 --output-dir")
            sys.exit(1)

        batch_path = Path(batch_file)
        if not batch_path.exists():
            logger.error(f"批量文件不存在: {batch_file}")
            sys.exit(1)

        object_paths = [
            line.strip()
            for line in batch_path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

        results = downloader.download_batch(
            bucket=bucket,
            object_paths=object_paths,
            output_dir=output_dir,
        )

        if not all(results.values()):
            logger.warning("部分文件下载失败")
            sys.exit(1)
        return

    # 模式3: 单文件下载
    if not bucket or not object_path or not output:
        logger.error("单文件下载需要指定 --bucket, --object-path, --output")
        logger.error("使用 --help 查看帮助")
        sys.exit(1)

    success = downloader.download(
        bucket=bucket,
        object_path=object_path,
        output=output,
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    fire.Fire(main)
