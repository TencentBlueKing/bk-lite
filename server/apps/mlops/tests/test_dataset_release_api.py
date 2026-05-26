import types
from unittest.mock import Mock

import pytest
from rest_framework import status

from apps.mlops.models.classification import (
    ClassificationDataset,
    ClassificationDatasetRelease,
    ClassificationTrainData,
)


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_classification_dataset_release_api_rejects_same_version_pending_release(
    monkeypatch,
    mlops_add_api_client,
):
    dataset = ClassificationDataset.objects.create(name="dataset-api", description="", team=[1])
    train = ClassificationTrainData.objects.create(name="train.csv", dataset=dataset, is_train_data=True)
    val = ClassificationTrainData.objects.create(name="val.csv", dataset=dataset, is_val_data=True)
    test = ClassificationTrainData.objects.create(name="test.csv", dataset=dataset, is_test_data=True)
    ClassificationDatasetRelease.objects.create(
        name="existing",
        description="",
        dataset=dataset,
        version="v9.0.0",
        dataset_file="existing.zip",
        status="pending",
        metadata={},
        file_size=1,
    )
    delay_mock = Mock()
    monkeypatch.setattr("apps.mlops.tasks.classification.publish_dataset_release_async.delay", delay_mock)

    response = mlops_add_api_client.post(
        "/api/v1/mlops/classification_dataset_releases/",
        {
            "dataset": dataset.id,
            "version": "v9.0.0",
            "train_file_id": train.id,
            "val_file_id": val.id,
            "test_file_id": test.id,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    delay_mock.assert_not_called()


def test_classification_dataset_release_api_retries_same_version_failed_release(
    monkeypatch,
    mlops_add_api_client,
):
    dataset = ClassificationDataset.objects.create(name="dataset-api-failed", description="", team=[1])
    train = ClassificationTrainData.objects.create(name="train.csv", dataset=dataset, is_train_data=True)
    val = ClassificationTrainData.objects.create(name="val.csv", dataset=dataset, is_val_data=True)
    test = ClassificationTrainData.objects.create(name="test.csv", dataset=dataset, is_test_data=True)
    failed_release = ClassificationDatasetRelease.objects.create(
        name="existing-failed",
        description="",
        dataset=dataset,
        version="v9.0.1",
        dataset_file="failed.zip",
        status="failed",
        metadata={"error": "boom"},
        file_size=10,
    )
    delay_mock = Mock(return_value=types.SimpleNamespace(id="task-1"))
    monkeypatch.setattr("apps.mlops.tasks.classification.publish_dataset_release_async.delay", delay_mock)

    response = mlops_add_api_client.post(
        "/api/v1/mlops/classification_dataset_releases/",
        {
            "dataset": dataset.id,
            "version": "v9.0.1",
            "train_file_id": train.id,
            "val_file_id": val.id,
            "test_file_id": test.id,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    failed_release.refresh_from_db()
    assert failed_release.status == "pending"
    assert failed_release.file_size == 0
    assert failed_release.metadata == {}
    delay_mock.assert_called_once_with(failed_release.id, train.id, val.id, test.id)
