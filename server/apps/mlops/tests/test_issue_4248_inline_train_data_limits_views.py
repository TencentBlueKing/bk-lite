"""Issue #4248 四类 HTTP 列表契约。"""

import pytest

from apps.mlops.tests._issue_4248_inline_helpers import HTTP_TRAIN_DATA_CASES, _classes, _install_file_reader

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("page_size", (None, "0", "-1"))
def test_http_list_rejects_unpaginated_inline_expansion_before_storage(
    monkeypatch,
    mlops_api_client,
    page_size,
):
    from apps.mlops.models.classification import ClassificationDataset, ClassificationTrainData

    dataset = ClassificationDataset.objects.create(
        name="dataset",
        description="",
        team=[1],
    )
    instances = ClassificationTrainData.objects.bulk_create(
        [
            ClassificationTrainData(
                name=f"train-{index}",
                dataset=dataset,
                train_data=f"fixtures/{index}.csv",
            )
            for index in range(21)
        ]
    )
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b"text,label\nhealthy,ok\n",
    )
    query = {"include_train_data": "true"}
    if page_size is not None:
        query["page_size"] = page_size

    response = mlops_api_client.get(
        "/api/v1/mlops/classification_train_data/",
        query,
    )

    assert response.status_code == 400
    assert response.data["error"] == "inline_train_data_limit_exceeded"
    assert response.data["reason"] == "list_items"
    assert reads == []


def test_http_list_budget_counts_only_current_team_records(
    monkeypatch,
    mlops_api_client,
):
    from apps.mlops.models.classification import ClassificationDataset, ClassificationTrainData

    visible_dataset = ClassificationDataset.objects.create(
        name="visible",
        description="",
        team=[1],
    )
    hidden_dataset = ClassificationDataset.objects.create(
        name="hidden",
        description="",
        team=[2],
    )
    visible = ClassificationTrainData.objects.create(
        name="visible",
        dataset=visible_dataset,
        train_data="fixtures/visible.csv",
    )
    hidden = ClassificationTrainData.objects.bulk_create(
        [
            ClassificationTrainData(
                name=f"hidden-{index}",
                dataset=hidden_dataset,
                train_data=f"fixtures/hidden-{index}.csv",
            )
            for index in range(100)
        ]
    )
    reads = _install_file_reader(
        monkeypatch,
        [visible, *hidden],
        b"text,label\nhealthy,ok\n",
    )

    response = mlops_api_client.get(
        "/api/v1/mlops/classification_train_data/",
        {"include_train_data": "true", "page_size": "-1"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.data] == [visible.id]
    assert reads == ["fixtures/visible.csv"]


@pytest.mark.parametrize(("suffix", "basename", "endpoint"), HTTP_TRAIN_DATA_CASES)
def test_all_http_train_data_lists_share_stable_limit_error(
    monkeypatch,
    mlops_api_client,
    suffix,
    basename,
    endpoint,
):
    _, Dataset, TrainData = _classes(suffix, basename)
    dataset = Dataset.objects.create(name="dataset", description="", team=[1])
    instances = TrainData.objects.bulk_create(
        [
            TrainData(
                name=f"train-{index}",
                dataset=dataset,
                train_data=f"fixtures/{index}.data",
            )
            for index in range(21)
        ]
    )
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b"text,label\nhealthy,ok\n",
    )

    response = mlops_api_client.get(
        f"/api/v1/mlops/{endpoint}/",
        {"include_train_data": "true", "page_size": "-1"},
    )

    assert response.status_code == 400
    assert response.data["error"] == "inline_train_data_limit_exceeded"
    assert response.data["reason"] == "list_items"
    assert reads == []


def test_http_inline_list_keeps_normal_paginated_response_contract(
    monkeypatch,
    mlops_api_client,
):
    from apps.mlops.models.classification import ClassificationDataset, ClassificationTrainData

    dataset = ClassificationDataset.objects.create(
        name="dataset",
        description="",
        team=[1],
    )
    instances = ClassificationTrainData.objects.bulk_create(
        [
            ClassificationTrainData(
                name=f"train-{index}",
                dataset=dataset,
                train_data=f"fixtures/{index}.csv",
            )
            for index in range(21)
        ]
    )
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b"text,label\nhealthy,ok\n",
    )

    response = mlops_api_client.get(
        "/api/v1/mlops/classification_train_data/",
        {"include_train_data": "true", "page": "1", "page_size": "10"},
    )

    assert response.status_code == 200
    assert response.data["count"] == 21
    assert len(response.data["items"]) == 10
    assert len(reads) == 10


def test_http_inline_list_denies_without_view_permission_before_storage(
    monkeypatch,
    mlops_api_client,
    mlops_user,
):
    from apps.mlops.models.classification import ClassificationDataset, ClassificationTrainData

    dataset = ClassificationDataset.objects.create(
        name="dataset",
        description="",
        team=[1],
    )
    instance = ClassificationTrainData.objects.create(
        name="train",
        dataset=dataset,
        train_data="fixtures/train.csv",
    )
    reads = _install_file_reader(
        monkeypatch,
        [instance],
        b"text,label\nhealthy,ok\n",
    )
    mlops_user.permission = {"mlops": set()}

    response = mlops_api_client.get(
        "/api/v1/mlops/classification_train_data/",
        {"include_train_data": "true", "page_size": "-1"},
    )

    assert response.status_code == 403
    assert reads == []
