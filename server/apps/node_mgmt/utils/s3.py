from apps.rpc.jetstream import JetStreamService


# 文件上传
async def upload_file_to_s3(file, s3_file_path):
    jetstream = JetStreamService()
    await jetstream.connect()
    # 读取文件数据
    file_data = file.read()  # 读取整个文件内容为字节流
    file_name = file.name  # 获取原始文件名
    await jetstream.put(s3_file_path, file_data, description=file_name)
    await jetstream.close()


# 下载文件
async def download_file_by_s3(s3_file_path):
    jetstream = JetStreamService()
    await jetstream.connect()
    file, name = await jetstream.get(s3_file_path)
    await jetstream.close()
    return file, name


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
