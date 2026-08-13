import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from nats.js.errors import ObjectNotFoundError

from apps.core.logger import node_logger as logger
from apps.rpc.jetstream import JetStreamService

JETSTREAM_CLOSE_TIMEOUT_SECONDS = 5


@asynccontextmanager
async def jetstream_connection(jetstream=None):
    """提供异常安全且有界的 JetStream 连接生命周期。"""
    jetstream = jetstream or JetStreamService()
    connection_ready = False
    operation_error = None
    try:
        await jetstream.connect()
        connection_ready = True
        yield jetstream
    except BaseException as error:
        operation_error = error
        raise
    finally:
        if connection_ready or getattr(jetstream, "nc", None) is not None:
            try:
                await asyncio.wait_for(
                    jetstream.close(),
                    timeout=JETSTREAM_CLOSE_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                logger.exception("Failed to close JetStream connection")
                if operation_error is None:
                    raise
            except Exception:
                logger.exception("Failed to close JetStream connection")


async def upload_file_to_s3(file, s3_file_path):
    async with jetstream_connection() as jetstream:
        if hasattr(file, "open"):
            file.open("rb")
        stream = getattr(file, "file", file)
        if hasattr(stream, "seek"):
            stream.seek(0)
        file_name = getattr(file, "name", getattr(stream, "name", s3_file_path))
        await jetstream.put(s3_file_path, stream, description=file_name)


async def download_file_by_s3(s3_file_path):
    async with jetstream_connection() as jetstream:
        return await jetstream.get(s3_file_path)


async def stream_download_file_by_s3(s3_file_path: str, chunk_size: int = 1024 * 1024) -> AsyncGenerator[tuple[bytes, str, int], None]:
    """
    流式下载文件，避免大文件内存堆积。

    Yields:
        tuple[bytes, str, int]: (chunk_data, filename, total_size)
    """
    async with jetstream_connection() as jetstream:
        async for chunk, filename, total_size in jetstream.get_streaming(s3_file_path, chunk_size):
            yield chunk, filename, total_size


# 删除文件
async def delete_s3_file(s3_file_path):
    async with jetstream_connection() as jetstream:
        await jetstream.delete(s3_file_path)


async def delete_s3_files(s3_file_paths: list[str], max_concurrency: int) -> dict[str, Exception | None]:
    """用单连接有界并发删除文件，逐 key 返回失败原因。

    重复 key 只删除一次；对象已不存在视为幂等成功，便于清理远端删除后、
    数据库删除前中断所遗留的记录。
    """
    unique_file_paths = list(dict.fromkeys(s3_file_paths))
    if not unique_file_paths:
        return {}

    results = {}
    file_paths = iter(unique_file_paths)

    async def delete_worker():
        for file_path in file_paths:
            try:
                await jetstream.delete(file_path)
            except ObjectNotFoundError:
                results[file_path] = None
            except Exception as error:
                results[file_path] = error
            else:
                results[file_path] = None

    async with jetstream_connection() as jetstream:
        worker_count = min(max(1, max_concurrency), len(unique_file_paths))
        await asyncio.gather(*(delete_worker() for _ in range(worker_count)))
    return {file_path: results[file_path] for file_path in unique_file_paths}


# 文件列表
async def list_s3_files():
    async with jetstream_connection() as jetstream:
        return await jetstream.list_objects()
