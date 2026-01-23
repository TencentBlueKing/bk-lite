from asgiref.sync import async_to_sync
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.installer import (
    WINDOWS_INSTALLER_FILENAME,
    WINDOWS_INSTALLER_S3_PATH,
)
from apps.node_mgmt.utils.s3 import download_file_by_s3


class InstallerViewSet(viewsets.ViewSet):
    @action(methods=["GET"], detail=False, url_path="download")
    def download(self, request):
        file, _ = async_to_sync(download_file_by_s3)(WINDOWS_INSTALLER_S3_PATH)
        return WebUtils.response_file(file, WINDOWS_INSTALLER_FILENAME)
