from django.core.management import BaseCommand

from apps.apm.services.probe_artifacts import JAVA_AGENT_ARTIFACT_NAME, PROBE_ARTIFACT_OBJECT_KEYS, upload_probe_artifact
from apps.core.logger import apm_logger as logger


class Command(BaseCommand):
    help = "APM 探针制品初始化 - 上传探针文件到对象存储，供接入脚本从系统内地址下载"

    def add_arguments(self, parser):
        parser.add_argument(
            "--artifact",
            type=str,
            choices=sorted(PROBE_ARTIFACT_OBJECT_KEYS),
            default=JAVA_AGENT_ARTIFACT_NAME,
            help="探针制品名称",
        )
        parser.add_argument(
            "--file_path",
            type=str,
            required=True,
            help="探针制品文件路径",
        )

    def handle(self, *args, **options):
        artifact_name = options["artifact"]
        file_path = options["file_path"]

        logger.info(f"APM 探针制品 {artifact_name} 初始化开始，文件路径: {file_path}")
        try:
            upload_probe_artifact(artifact_name, file_path)
        except FileNotFoundError:
            logger.error(f"文件不存在: {file_path}")
            raise
        except Exception as e:
            logger.error(f"APM 探针制品 {artifact_name} 上传失败: {e}")
            raise
        logger.info(f"APM 探针制品 {artifact_name} 初始化完成，对象路径: {PROBE_ARTIFACT_OBJECT_KEYS[artifact_name]}")
