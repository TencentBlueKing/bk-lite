from django.core.files.base import ContentFile
from apps.node_mgmt.utils.s3 import upload_file_to_s3, download_file_by_s3, delete_s3_file, list_s3_files
from asgiref.sync import async_to_sync


class PackageService:
    @staticmethod
    def upload_file(file: ContentFile, data):
        s3_file_path = f"{data['os']}/{data['object']}/{data['version']}/{data['name']}"
        async_to_sync(upload_file_to_s3)(file, s3_file_path)

    @staticmethod
    def download_file(package_obj):
        s3_file_path = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
        return async_to_sync(download_file_by_s3)(s3_file_path)

    @staticmethod
    def delete_file(package_obj):
        s3_file_path = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
        async_to_sync(delete_s3_file)(s3_file_path)

    @staticmethod
    def list_files():
        files = async_to_sync(list_s3_files)()
        files = [
            {
                "name": file.name,
                "nuid": file.nuid,
                "description": file.description,
                "deleted": file.deleted,
            }
            for file in files
        ]
        return files


# from config.components.temp_upload import FILE_UPLOAD_TEMP_DIR
# from django.core.files.storage import default_storage

# class PackageService:
#     @staticmethod
#     def upload_file(file: ContentFile, data):
#         # 上传文件到S3
#         s3_file_path = f"{data['os']}/{data['object']}/{data['version']}/{data['name']}"
#         upload_file_to_s3(file, s3_file_path)
#
#         # local_file_path = f"{FILE_UPLOAD_TEMP_DIR}/{package_obj.name}"
#         #
#         # # 接收文件到指定目录
#         # default_storage.save(local_file_path, ContentFile(file.read()))
#         # s3_file_path = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
#         # # 从指定目录上传文件到s3
#         # upload_file_to_s3(local_file_path, s3_file_path)
#         #
#         # # 删除临时文件
#         # if default_storage.exists(local_file_path):
#         #     default_storage.delete(local_file_path)
#
#     @staticmethod
#     def download_file(package_obj):
#         s3_file_path = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
#         return download_file_by_s3(s3_file_path)
#
#     @staticmethod
#     def delete_file(package_obj):
#         s3_file_path = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
#         # 删除文件
#         delete_s3_file(s3_file_path)
