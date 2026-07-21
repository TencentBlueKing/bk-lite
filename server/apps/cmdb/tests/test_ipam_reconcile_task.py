import pytest
from unittest.mock import patch

pytestmark = pytest.mark.django_db


def test_periodic_reconcile_task_enqueues_job():
    from apps.cmdb.tasks.celery_tasks import reconcile_ipam_task

    with patch("apps.cmdb.services.ipam_reconcile_job.IPAMReconcileJob.enqueue") as enqueue:
        enqueue.return_value.run.run_id = "run-1"
        enqueue.return_value.run.status = "pending"
        enqueue.return_value.reused = False
        out = reconcile_ipam_task()

    enqueue.assert_called_once_with(trigger="scheduled")
    assert out == {"run_id": "run-1", "status": "pending", "reused": False}


def test_reconcile_worker_task_executes_named_run():
    from apps.cmdb.tasks.celery_tasks import execute_ipam_reconcile_task

    with patch(
        "apps.cmdb.services.ipam_reconcile_job.IPAMReconcileJob.execute",
        return_value={"created": 2},
    ) as execute:
        out = execute_ipam_reconcile_task("run-1")

    execute.assert_called_once_with("run-1")
    assert out == {"created": 2}
