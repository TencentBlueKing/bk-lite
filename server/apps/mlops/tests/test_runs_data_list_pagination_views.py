import types

import pandas as pd
import pytest
from rest_framework import status

from apps.base.tests.factories import UserFactory
from apps.mlops.constants import TrainJobStatus
from apps.mlops.tests.test_views_actions_param import (
    ALGOS,
    ALGO_IDS,
    _call,
    _make_train_job,
    _patch_mlflow,
    _view_module,
    factory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def superuser():
    return UserFactory(username="mlops-pagination-su", domain="domain.com", roles=[], is_superuser=True)


def _runs_frame():
    start_time = pd.Timestamp("2020-01-01 00:00:00", tz="UTC")
    end_time = pd.Timestamp("2020-01-01 00:10:00", tz="UTC")
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "status": "FINISHED",
                "start_time": start_time,
                "end_time": end_time,
                "tags.mlflow.runName": run_name,
            }
            for run_id, run_name in (("r1", "first"), ("r2", "second"), ("r3", "third"))
        ]
    )


def _get_runs_response(monkeypatch, superuser, suffix, model_module, basename, query):
    train_job = _make_train_job(model_module, basename, status_value=TrainJobStatus.COMPLETED)
    module = _view_module(suffix)
    runs = _runs_frame()
    _patch_mlflow(
        monkeypatch,
        suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda experiment_id, **kwargs: runs,
    )
    view = getattr(module, f"{basename}TrainJobViewSet").as_view({"get": "get_run_data_list"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs_data_list/?{query}")
    return _call(view, request, superuser, pk=train_job.id)


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
@pytest.mark.parametrize(
    "query",
    [
        "page=0&page_size=2",
        "page=-1&page_size=2",
        "page=abc&page_size=2",
        "page=1&page_size=abc",
        "page=1&page_size=-2",
    ],
)
def test_runs_data_list_rejects_invalid_pagination(
    monkeypatch,
    superuser,
    suffix,
    prefix,
    model_module,
    basename,
    query,
):
    response = _get_runs_response(monkeypatch, superuser, suffix, model_module, basename, query)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {"error": "分页参数必须为正整数"}


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_runs_data_list_preserves_valid_pagination(
    monkeypatch,
    superuser,
    suffix,
    prefix,
    model_module,
    basename,
):
    response = _get_runs_response(
        monkeypatch,
        superuser,
        suffix,
        model_module,
        basename,
        "page=2&page_size=2",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 3
    assert [item["run_id"] for item in response.data["items"]] == ["r3"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
@pytest.mark.parametrize("page_size", ["0", "-1"])
def test_runs_data_list_preserves_unpaginated_page_size(
    monkeypatch,
    superuser,
    suffix,
    prefix,
    model_module,
    basename,
    page_size,
):
    response = _get_runs_response(
        monkeypatch,
        superuser,
        suffix,
        model_module,
        basename,
        f"page=1&page_size={page_size}",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 3
    assert [item["run_id"] for item in response.data["items"]] == ["r1", "r2", "r3"]
