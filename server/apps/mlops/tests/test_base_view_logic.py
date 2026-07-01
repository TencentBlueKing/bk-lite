import pydantic.root_model  # noqa

import pandas as pd
import pytest

from apps.mlops.constants import MLflowRunStatus, TrainJobStatus
from apps.mlops.models.anomaly_detection import AnomalyDetectionTrainJob
from apps.mlops.views.anomaly_detection import AnomalyDetectionTrainJobViewSet

pytestmark = pytest.mark.unit


# ----------------- has_run_in_runs_frame -----------------


def test_has_run_in_runs_frame_none():
    assert AnomalyDetectionTrainJobViewSet.has_run_in_runs_frame(None, "r1") is False


def test_has_run_in_runs_frame_empty():
    df = pd.DataFrame({"run_id": []})
    assert AnomalyDetectionTrainJobViewSet.has_run_in_runs_frame(df, "r1") is False


def test_has_run_in_runs_frame_found():
    df = pd.DataFrame({"run_id": ["r1", "r2"]})
    assert AnomalyDetectionTrainJobViewSet.has_run_in_runs_frame(df, "r1") is True


def test_has_run_in_runs_frame_string_coercion():
    df = pd.DataFrame({"run_id": [123, 456]})
    assert AnomalyDetectionTrainJobViewSet.has_run_in_runs_frame(df, "123") is True


def test_has_run_in_runs_frame_not_found():
    df = pd.DataFrame({"run_id": ["r1"]})
    assert AnomalyDetectionTrainJobViewSet.has_run_in_runs_frame(df, "rX") is False


# ----------------- run_not_found_response -----------------


def test_run_not_found_response_shape():
    resp = AnomalyDetectionTrainJobViewSet.run_not_found_response("r9")
    assert resp.status_code == 404
    assert resp.data["code"] == "run_not_found"
    assert resp.data["run_id"] == "r9"


# ----------------- annotate_run_delete_eligibility -----------------


def test_annotate_empty_returns_input():
    assert AnomalyDetectionTrainJobViewSet.annotate_run_delete_eligibility([], TrainJobStatus.RUNNING) == []


def test_annotate_rule1_not_running_all_deletable():
    runs = [
        {"run_id": "a", "status": MLflowRunStatus.RUNNING},
        {"run_id": "b", "status": "FINISHED"},
    ]
    AnomalyDetectionTrainJobViewSet.annotate_run_delete_eligibility(runs, TrainJobStatus.COMPLETED)
    assert runs[0]["is_latest_run"] is True
    assert all(r["can_delete_run"] for r in runs)
    assert all(r["delete_block_reason"] is None for r in runs)


def test_annotate_rule2_latest_running_blocks_latest_only():
    runs = [
        {"run_id": "latest", "status": MLflowRunStatus.RUNNING},
        {"run_id": "stale", "status": MLflowRunStatus.RUNNING},
        {"run_id": "done", "status": "FINISHED"},
    ]
    AnomalyDetectionTrainJobViewSet.annotate_run_delete_eligibility(runs, TrainJobStatus.RUNNING)
    assert runs[0]["can_delete_run"] is False
    assert runs[0]["delete_block_reason"] == "active_latest_run"
    # stale RUNNING run is deletable
    assert runs[1]["can_delete_run"] is True
    assert runs[2]["can_delete_run"] is True


def test_annotate_rule3_inconsistent_blocks_running_rows():
    # TrainJob running but latest run is not RUNNING -> fail closed
    runs = [
        {"run_id": "latest", "status": "FINISHED"},
        {"run_id": "ghost", "status": MLflowRunStatus.RUNNING},
        {"run_id": "ok", "status": "FAILED"},
    ]
    AnomalyDetectionTrainJobViewSet.annotate_run_delete_eligibility(runs, TrainJobStatus.RUNNING)
    assert runs[0]["can_delete_run"] is True  # latest finished -> deletable
    assert runs[1]["can_delete_run"] is False
    assert runs[1]["delete_block_reason"] == "inconsistent_state"
    assert runs[2]["can_delete_run"] is True


def test_annotate_ambiguous_latest_duplicate_run_ids():
    runs = [
        {"run_id": "dup", "status": MLflowRunStatus.RUNNING},
        {"run_id": "dup", "status": MLflowRunStatus.RUNNING},
    ]
    AnomalyDetectionTrainJobViewSet.annotate_run_delete_eligibility(runs, TrainJobStatus.RUNNING)
    # ambiguous -> running rows blocked when job running
    assert all(r["is_latest_run"] is False for r in runs)
    assert all(r["can_delete_run"] is False for r in runs)
    assert all(r["delete_block_reason"] == "ambiguous_latest_run" for r in runs)


def test_annotate_ambiguous_latest_non_running_deletable():
    runs = [
        {"run_id": "dup", "status": "FINISHED"},
        {"run_id": "dup", "status": "FINISHED"},
    ]
    AnomalyDetectionTrainJobViewSet.annotate_run_delete_eligibility(runs, TrainJobStatus.RUNNING)
    assert all(r["can_delete_run"] is True for r in runs)


# ----------------- check_run_delete_eligibility -----------------


def _make_runs_frame(rows):
    return pd.DataFrame(rows)


def test_check_run_delete_eligibility_no_runs(monkeypatch):
    vs = AnomalyDetectionTrainJobViewSet()
    monkeypatch.setattr(vs, "get_train_job_runs", lambda tj: None)
    tj = AnomalyDetectionTrainJob(status=TrainJobStatus.COMPLETED)
    allowed, reason = vs.check_run_delete_eligibility("r1", tj)
    assert allowed is False
    assert reason == "run_not_found"


def test_check_run_delete_eligibility_run_missing(monkeypatch):
    vs = AnomalyDetectionTrainJobViewSet()
    frame = _make_runs_frame([{"run_id": "other", "status": "FINISHED"}])
    monkeypatch.setattr(vs, "get_train_job_runs", lambda tj: frame)
    tj = AnomalyDetectionTrainJob(status=TrainJobStatus.COMPLETED)
    allowed, reason = vs.check_run_delete_eligibility("r1", tj)
    assert allowed is False
    assert reason == "run_not_found"


def test_check_run_delete_eligibility_allowed(monkeypatch):
    vs = AnomalyDetectionTrainJobViewSet()
    frame = _make_runs_frame([{"run_id": "r1", "status": "FINISHED"}])
    monkeypatch.setattr(vs, "get_train_job_runs", lambda tj: frame)
    tj = AnomalyDetectionTrainJob(status=TrainJobStatus.COMPLETED)
    allowed, reason = vs.check_run_delete_eligibility("r1", tj)
    assert allowed is True
    assert reason is None


def test_check_run_delete_eligibility_blocked(monkeypatch):
    vs = AnomalyDetectionTrainJobViewSet()
    frame = _make_runs_frame([{"run_id": "r1", "status": MLflowRunStatus.RUNNING}])
    monkeypatch.setattr(vs, "get_train_job_runs", lambda tj: frame)
    tj = AnomalyDetectionTrainJob(status=TrainJobStatus.RUNNING)
    allowed, reason = vs.check_run_delete_eligibility("r1", tj)
    assert allowed is False
    assert reason == "active_latest_run"


# ----------------- claim_train_job_running / restore (DB) -----------------


@pytest.mark.django_db
def test_claim_train_job_running_success():
    tj = AnomalyDetectionTrainJob.objects.create(
        name="j1", description="", team=[1], status=TrainJobStatus.PENDING,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    vs = AnomalyDetectionTrainJobViewSet()
    prev = vs.claim_train_job_running(tj)
    assert prev == TrainJobStatus.PENDING
    assert tj.status == TrainJobStatus.RUNNING
    tj.refresh_from_db()
    assert tj.status == TrainJobStatus.RUNNING


@pytest.mark.django_db
def test_claim_train_job_running_already_running_returns_none():
    tj = AnomalyDetectionTrainJob.objects.create(
        name="j2", description="", team=[1], status=TrainJobStatus.RUNNING,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    vs = AnomalyDetectionTrainJobViewSet()
    assert vs.claim_train_job_running(tj) is None


@pytest.mark.django_db
def test_restore_train_job_status_restores_when_running():
    tj = AnomalyDetectionTrainJob.objects.create(
        name="j3", description="", team=[1], status=TrainJobStatus.RUNNING,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    AnomalyDetectionTrainJobViewSet.restore_train_job_status(tj, TrainJobStatus.PENDING)
    tj.refresh_from_db()
    assert tj.status == TrainJobStatus.PENDING
    assert tj.status == TrainJobStatus.PENDING


@pytest.mark.django_db
def test_restore_train_job_status_noop_when_not_running():
    tj = AnomalyDetectionTrainJob.objects.create(
        name="j4", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    AnomalyDetectionTrainJobViewSet.restore_train_job_status(tj, TrainJobStatus.PENDING)
    tj.refresh_from_db()
    # not RUNNING -> no update applied
    assert tj.status == TrainJobStatus.COMPLETED
