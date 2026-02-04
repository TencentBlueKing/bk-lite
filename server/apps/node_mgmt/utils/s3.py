from typing import AsyncGenerator

from apps.rpc.jetstream import JetStreamService


async def upload_file_to_s3(file, s3_file_path):
    jetstream = JetStreamService()
    await jetstream.connect()
    file_data = file.read()
    file_name = file.name
    await jetstream.put(s3_file_path, file_data, description=file_name)
    await jetstream.close()


async def download_file_by_s3(s3_file_path):
    jetstream = JetStreamService()
    await jetstream.connect()
    file, name = await jetstream.get(s3_file_path)
    await jetstream.close()
    return file, name


async def stream_download_file_by_s3(
    s3_file_path: str, chunk_size: int = 1024 * 1024
) -> AsyncGenerator[tuple[bytes, str, int], None]:
    """
    流式下载文件，避免大文件内存堆积。

    Yields:
        tuple[bytes, str, int]: (chunk_data, filename, total_size)
    """
    jetstream = JetStreamService()
    await jetstream.connect()
    try:
        async for chunk, filename, total_size in jetstream.get_streaming(
            s3_file_path, chunk_size
        ):
            yield chunk, filename, total_size
    finally:
        await jetstream.close()


# 删除文件
async def delete_s3_file(s3_file_path):
    jetstream = JetStreamService()
    await jetstream.connect()
    await jetstream.delete(s3_file_path)
    await jetstream.close()


# 文件列表
async def list_s3_files():
    jetstream = JetStreamService()
    await jetstream.connect()
    entries = await jetstream.list_objects()
    await jetstream.close()
    return entries
