import asyncio
from typing import AsyncGenerator

from nats.js.errors import ObjectNotFoundError

from apps.rpc.jetstream import JetStreamService


async def upload_file_to_s3(file, s3_file_path):
    jetstream = JetStreamService()
    await jetstream.connect()
    if hasattr(file, "open"):
        file.open("rb")
    stream = getattr(file, "file", file)
    if hasattr(stream, "seek"):
        stream.seek(0)
    file_name = getattr(file, "name", getattr(stream, "name", s3_file_path))
    await jetstream.put(s3_file_path, stream, description=file_name)
    await jetstream.close()


async def download_file_by_s3(s3_file_path):
    jetstream = JetStreamService()
    await jetstream.connect()
    file, name = await jetstream.get(s3_file_path)
    await jetstream.close()
    return file, name


async def stream_download_file_by_s3(s3_file_path: str, chunk_size: int = 1024 * 1024) -> AsyncGenerator[tuple[bytes, str, int], None]:
    """
    流式下载文件，避免大文件内存堆积。

    Yields:
        tuple[bytes, str, int]: (chunk_data, filename, total_size)
    """
    jetstream = JetStreamService()
    await jetstream.connect()
    try:
        async for chunk, filename, total_size in jetstream.get_streaming(s3_file_path, chunk_size):
            yield chunk, filename, total_size
    finally:
        await jetstream.close()


# 删除文件
async def delete_s3_file(s3_file_path):
    jetstream = JetStreamService()
    await jetstream.connect()
    await jetstream.delete(s3_file_path)
    await jetstream.close()


async def delete_s3_files(s3_file_paths: list[str], max_concurrency: int) -> dict[str, Exception | None]:
    """用单连接有界并发删除文件，逐 key 返回失败原因。

    重复 key 只删除一次；对象已不存在视为幂等成功，便于清理远端删除后、
    数据库删除前中断所遗留的记录。
    """
    unique_file_paths = list(dict.fromkeys(s3_file_paths))
    if not unique_file_paths:
        return {}

    jetstream = JetStreamService()
    connection_ready = False
    errors = {}
    file_paths = iter(unique_file_paths)

    async def delete_worker():
        for file_path in file_paths:
            try:
                await jetstream.delete(file_path)
            except ObjectNotFoundError:
                errors[file_path] = None
            except Exception as error:
                errors[file_path] = error
            else:
                errors[file_path] = None

    try:
        await jetstream.connect()
        connection_ready = True
        worker_count = min(max(1, max_concurrency), len(unique_file_paths))
        await asyncio.gather(*(delete_worker() for _ in range(worker_count)))
    finally:
        if connection_ready or getattr(jetstream, "nc", None) is not None:
            await jetstream.close()
    return {file_path: errors[file_path] for file_path in unique_file_paths}


# 文件列表
async def list_s3_files():
    jetstream = JetStreamService()
    await jetstream.connect()
    entries = await jetstream.list_objects()
    await jetstream.close()
    return entries
