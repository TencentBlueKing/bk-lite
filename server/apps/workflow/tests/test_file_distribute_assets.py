from datetime import timedelta

import pytest
from django.utils import timezone

import apps.workflow.services.file_distribute_assets as file_distribute_assets
from apps.workflow.services.file_distribute_assets import collect_file_distribute_keys, renew_workflow_file_distribute_assets


def test_importing_file_distribute_assets_does_not_bind_job_models():
    assert not hasattr(file_distribute_assets, "renew_distribution_files")


def test_renew_skips_when_job_mgmt_is_not_installed(monkeypatch):
    monkeypatch.setattr(file_distribute_assets.django_apps, "is_installed", lambda label: label != "apps.job_mgmt")
    updated = renew_workflow_file_distribute_assets(
        definition={
            "tasks": [
                {
                    "name": "bklite_file_distribute",
                    "inputParameters": {"files": [{"file_key": "job-files/a.conf", "name": "a.conf"}]},
                }
            ]
        },
        team=[7],
    )
    assert updated == 0


def test_collect_file_distribute_keys_from_definition():
    keys = collect_file_distribute_keys(
        {
            "tasks": [
                {
                    "name": "bklite_file_distribute",
                    "inputParameters": {
                        "files": [
                            {"file_key": "job-files/a.conf", "name": "a.conf"},
                            {"file_key": "job-files/a.conf", "name": "dup"},
                            {"file_key": "job-files/b.conf", "name": "b.conf"},
                        ]
                    },
                },
                {"name": "bklite_job_execute", "inputParameters": {"files": [{"file_key": "ignored"}]}},
            ]
        }
    )
    assert keys == ["job-files/a.conf", "job-files/b.conf"]


@pytest.mark.django_db
def test_renew_workflow_file_distribute_assets_extends_expire():
    from django.apps import apps as django_apps

    if not django_apps.is_installed("apps.job_mgmt"):
        pytest.skip("job_mgmt 未安装")
    from apps.job_mgmt.models import DistributionFile

    now = timezone.now()
    owned = DistributionFile.objects.create(
        original_name="a.conf",
        file_key="job-files/a.conf",
        expire_at=now + timedelta(days=1),
        team=7,
    )
    other_team = DistributionFile.objects.create(
        original_name="b.conf",
        file_key="job-files/b.conf",
        expire_at=now + timedelta(days=1),
        team=9,
    )

    updated = renew_workflow_file_distribute_assets(
        definition={
            "tasks": [
                {
                    "name": "bklite_file_distribute",
                    "inputParameters": {
                        "files": [
                            {"file_key": "job-files/a.conf", "name": "a.conf"},
                            {"file_key": "job-files/b.conf", "name": "b.conf"},
                            {"file_key": "job-files/missing.conf", "name": "missing.conf"},
                        ]
                    },
                }
            ]
        },
        team=[7],
    )

    owned.refresh_from_db()
    other_team.refresh_from_db()
    assert updated == 1
    assert owned.expire_at >= now + timedelta(days=89)
    assert other_team.expire_at < now + timedelta(days=2)
