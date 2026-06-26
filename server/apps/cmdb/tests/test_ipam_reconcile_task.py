import pytest
from unittest.mock import patch

pytestmark = pytest.mark.django_db


def test_reconcile_task_calls_service():
    from apps.cmdb.tasks.celery_tasks import reconcile_ipam_task
    with patch("apps.cmdb.services.ipam_reconcile.run_reconciliation",
               return_value={"created": 2}) as m:
        out = reconcile_ipam_task()
    m.assert_called_once()
    assert out["created"] == 2
