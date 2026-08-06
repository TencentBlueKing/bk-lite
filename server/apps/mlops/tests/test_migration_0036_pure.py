from importlib import import_module

import pytest
from django.conf import settings
from django.db.migrations.operations.fields import RemoveField
from django.db.migrations.operations.models import DeleteModel


pytestmark = pytest.mark.unit


if not settings.configured:
    settings.configure(
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="test-access-key",
        MINIO_SECRET_KEY="test-secret-key",
        MINIO_USE_HTTPS=False,
        MINIO_PUBLIC_BUCKETS=["munchkin-public"],
    )


def test_0036_deletes_train_history_models_without_removing_their_fields_first():
    migration = import_module("apps.mlops.migrations.0036_anomalydetectiondatasetrelease_and_more").Migration
    removed_models = {
        operation.model_name
        for operation in migration.operations
        if isinstance(operation, RemoveField)
    }
    deleted_models = {
        operation.name.lower()
        for operation in migration.operations
        if isinstance(operation, DeleteModel)
    }

    assert {"logclusteringtrainhistory", "timeseriespredicttrainhistory"}.isdisjoint(removed_models)
    assert {"logclusteringtrainhistory", "timeseriespredicttrainhistory"}.issubset(deleted_models)
