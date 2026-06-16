"""分发文件上传视图测试"""

from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.job_mgmt.models import DistributionFile

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/distribution_file/upload/"


class TestDistributionFileUpload:
    def test_upload_creates_record_with_current_team(self, su_client):
        f = SimpleUploadedFile("app.tar.gz", b"payload", content_type="application/gzip")
        with patch("apps.job_mgmt.views.distribution_file.async_to_sync", lambda fn: (lambda *a, **k: None)):
            resp = su_client.post(URL, {"file": f}, format="multipart")
        assert resp.status_code == 201
        assert resp.data["name"] == "app.tar.gz"
        df = DistributionFile.objects.get(id=resp.data["id"])
        assert df.team == 1
        assert df.original_name == "app.tar.gz"
        assert df.file_key.endswith(".gz")

    def test_upload_requires_file(self, su_client):
        with patch("apps.job_mgmt.views.distribution_file.async_to_sync", lambda fn: (lambda *a, **k: None)):
            resp = su_client.post(URL, {}, format="multipart")
        assert resp.status_code == 400
