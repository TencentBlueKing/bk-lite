"""
Tests for get_mlops_module_data NATS handler defensive input validation.

Issue #3493: 裸字典取键无校验导致 KeyError 崩溃 worker，page_size 无上界可 OOM。

These tests are Django-free and use sys.modules injection to load the module
without triggering Django setup or DB access.
"""
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _install(name, **attrs):
    """Install a fake module into sys.modules."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_nats_api():
    """Load nats_api.py without Django or real model imports."""
    # Fake nats_client with a no-op register decorator
    fake_nats_client = _install("nats_client")
    fake_nats_client.register = lambda fn: fn

    # Fake model factory: returns a MagicMock representing a Django model class
    def _fake_model(label):
        m = MagicMock(name=label)
        return m

    # Inject fake model modules
    for pkg in [
        "apps",
        "apps.mlops",
        "apps.mlops.models",
        "apps.mlops.models.anomaly_detection",
        "apps.mlops.models.classification",
        "apps.mlops.models.image_classification",
        "apps.mlops.models.log_clustering",
        "apps.mlops.models.object_detection",
        "apps.mlops.models.timeseries_predict",
    ]:
        _install(pkg)

    # Populate each model submodule with the classes referenced by nats_api.py
    model_attrs = {
        "apps.mlops.models.anomaly_detection": [
            "AnomalyDetectionDataset",
            "AnomalyDetectionDatasetRelease",
            "AnomalyDetectionServing",
            "AnomalyDetectionTrainData",
            "AnomalyDetectionTrainJob",
        ],
        "apps.mlops.models.classification": [
            "ClassificationDataset",
            "ClassificationDatasetRelease",
            "ClassificationServing",
            "ClassificationTrainData",
            "ClassificationTrainJob",
        ],
        "apps.mlops.models.image_classification": [
            "ImageClassificationDataset",
            "ImageClassificationDatasetRelease",
            "ImageClassificationServing",
            "ImageClassificationTrainData",
            "ImageClassificationTrainJob",
        ],
        "apps.mlops.models.log_clustering": [
            "LogClusteringDataset",
            "LogClusteringDatasetRelease",
            "LogClusteringServing",
            "LogClusteringTrainData",
            "LogClusteringTrainJob",
        ],
        "apps.mlops.models.object_detection": [
            "ObjectDetectionDataset",
            "ObjectDetectionDatasetRelease",
            "ObjectDetectionServing",
            "ObjectDetectionTrainData",
            "ObjectDetectionTrainJob",
        ],
        "apps.mlops.models.timeseries_predict": [
            "TimeSeriesPredictDataset",
            "TimeSeriesPredictDatasetRelease",
            "TimeSeriesPredictServing",
            "TimeSeriesPredictTrainData",
            "TimeSeriesPredictTrainJob",
        ],
    }
    for mod_name, attrs in model_attrs.items():
        mod = sys.modules[mod_name]
        for attr in attrs:
            setattr(mod, attr, _fake_model(attr))

    # Load the actual module under test via its file path
    file_path = os.path.join(
        os.path.dirname(__file__), "..", "nats_api.py"
    )
    spec = importlib.util.spec_from_file_location("mlops_nats_api", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Load once for all tests in this module
_nats_api = _load_nats_api()
_get_mlops_module_data = _nats_api.get_mlops_module_data
_MAX_PAGE_SIZE = _nats_api.MAX_PAGE_SIZE


class TestGetMlopsModuleDataValidation(unittest.TestCase):
    """Verify defensive guards added in fix for issue #3493."""

    def _make_mock_queryset(self, items):
        """Build a mock queryset that supports .filter(), .count(), .values()."""
        qs = MagicMock()
        filtered_qs = MagicMock()
        qs.objects.filter.return_value = filtered_qs
        filtered_qs.count.return_value = len(items)
        # Simulate slicing: values() returns an object whose slice is the items list
        values_mock = MagicMock()
        values_mock.__getitem__ = lambda self, sl: items[sl]
        filtered_qs.values.return_value = values_mock
        return qs

    def test_unknown_module_returns_error_not_keyerror(self):
        """Non-existent module must return error dict, not raise KeyError."""
        result = _get_mlops_module_data(
            module="no_such_module",
            child_module="anything",
            page=1,
            page_size=10,
            group_id=1,
        )
        self.assertFalse(result["result"], "Expected result=False for unknown module")
        self.assertIn("未知模块", result["message"])

    def test_unknown_child_module_returns_error_not_keyerror(self):
        """Non-existent child_module within a valid module must return error dict."""
        result = _get_mlops_module_data(
            module="dataset",
            child_module="no_such_child",
            page=1,
            page_size=10,
            group_id=1,
        )
        self.assertFalse(result["result"], "Expected result=False for unknown child_module")
        self.assertIn("未知子模块", result["message"])

    def test_page_size_capped_at_max(self):
        """Oversized page_size must be clamped to MAX_PAGE_SIZE."""
        # Track the slice argument passed to queryset[start:end]
        slices_seen = []

        fake_qs = MagicMock()
        fake_qs.count.return_value = 0

        # Use a real class so __getitem__ is a proper Mock
        class FakeValuesQS:
            def __getitem__(self, sl):
                slices_seen.append(sl)
                return []

        fake_qs.values.return_value = FakeValuesQS()

        fake_model = MagicMock()
        fake_model.objects.filter.return_value = fake_qs

        original_registry = _nats_api._get_module_registry

        def patched_registry():
            reg = original_registry()
            reg["dataset"]["anomaly_detection_dataset"] = (fake_model, "team")
            return reg

        with patch.object(_nats_api, "_get_module_registry", patched_registry):
            _get_mlops_module_data(
                module="dataset",
                child_module="anomaly_detection_dataset",
                page=1,
                page_size=999999,
                group_id=1,
                actor_context={"is_superuser": True},
            )

        # Verify the queryset was sliced with a capped end index
        # start=0, end=min(999999, MAX_PAGE_SIZE)
        self.assertEqual(len(slices_seen), 1, "queryset should be sliced exactly once")
        sl = slices_seen[0]
        self.assertEqual(sl.stop, _MAX_PAGE_SIZE, f"page_size should be capped at {_MAX_PAGE_SIZE}, got {sl.stop}")

    def test_page_size_negative_clamped_to_one(self):
        """page_size=-1 must be clamped to 1 (not -1) to avoid Django negative-index AssertionError."""
        slices_seen = []

        fake_qs = MagicMock()
        fake_qs.count.return_value = 0

        class FakeValuesQS:
            def __getitem__(self, sl):
                slices_seen.append(sl)
                return []

        fake_qs.values.return_value = FakeValuesQS()

        fake_model = MagicMock()
        fake_model.objects.filter.return_value = fake_qs

        original_registry = _nats_api._get_module_registry

        def patched_registry():
            reg = original_registry()
            reg["dataset"]["anomaly_detection_dataset"] = (fake_model, "team")
            return reg

        with patch.object(_nats_api, "_get_module_registry", patched_registry):
            result = _get_mlops_module_data(
                module="dataset",
                child_module="anomaly_detection_dataset",
                page=1,
                page_size=-1,
                group_id=1,
                actor_context={"is_superuser": True},
            )

        # Must succeed (not raise AssertionError from Django negative slice)
        self.assertTrue(result["result"])
        # page_size must be clamped to at least 1, so end = 1 * 1 = 1 (non-negative)
        self.assertEqual(len(slices_seen), 1)
        sl = slices_seen[0]
        self.assertGreaterEqual(sl.stop, 0, "end index must be non-negative to avoid Django AssertionError")

    def test_valid_request_returns_result_true(self):
        """Valid module/child_module returns result=True with count and items."""
        fake_qs = MagicMock()
        fake_qs.count.return_value = 2
        values_mock = MagicMock()
        values_mock.__getitem__ = lambda self, sl: [
            {"id": 1, "name": "foo"},
            {"id": 2, "name": "bar"},
        ]
        fake_qs.values.return_value = values_mock

        fake_model = MagicMock()
        fake_model.objects.filter.return_value = fake_qs

        original_registry = _nats_api._get_module_registry

        def patched_registry():
            reg = original_registry()
            reg["dataset"]["anomaly_detection_dataset"] = (fake_model, "team")
            return reg

        with patch.object(_nats_api, "_get_module_registry", patched_registry):
            result = _get_mlops_module_data(
                module="dataset",
                child_module="anomaly_detection_dataset",
                page=1,
                page_size=10,
                group_id=42,
                actor_context={"is_superuser": True},
            )

        self.assertTrue(result["result"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["items"]), 2)

    def test_missing_actor_context_is_rejected(self):
        """Calls without trusted user context must not choose an arbitrary group_id."""
        result = _get_mlops_module_data(
            module="dataset",
            child_module="anomaly_detection_dataset",
            page=1,
            page_size=10,
            group_id=42,
        )

        self.assertFalse(result["result"])
        self.assertIn("调用方上下文", result["message"])

    def test_unauthorized_group_id_is_rejected_before_query(self):
        """Non-superusers may only query MLOps data for groups in actor_context.group_list."""
        fake_model = MagicMock()

        original_registry = _nats_api._get_module_registry

        def patched_registry():
            reg = original_registry()
            reg["dataset"]["anomaly_detection_dataset"] = (fake_model, "team")
            return reg

        with patch.object(_nats_api, "_get_module_registry", patched_registry):
            result = _get_mlops_module_data(
                module="dataset",
                child_module="anomaly_detection_dataset",
                page=1,
                page_size=10,
                group_id=42,
                actor_context={"is_superuser": False, "group_list": [1, 2]},
            )

        self.assertFalse(result["result"])
        self.assertIn("无权访问该组织", result["message"])
        fake_model.objects.filter.assert_not_called()

    def test_authorized_group_id_filters_queryset(self):
        """Authorized non-superuser requests should still return the selected group's data."""
        fake_qs = MagicMock()
        fake_qs.count.return_value = 1
        values_mock = MagicMock()
        values_mock.__getitem__ = lambda self, sl: [{"id": 1, "name": "foo"}]
        fake_qs.values.return_value = values_mock

        fake_model = MagicMock()
        fake_model.objects.filter.return_value = fake_qs

        original_registry = _nats_api._get_module_registry

        def patched_registry():
            reg = original_registry()
            reg["dataset"]["anomaly_detection_dataset"] = (fake_model, "team")
            return reg

        with patch.object(_nats_api, "_get_module_registry", patched_registry):
            result = _get_mlops_module_data(
                module="dataset",
                child_module="anomaly_detection_dataset",
                page=1,
                page_size=10,
                group_id=42,
                actor_context={"is_superuser": False, "group_list": [1, "42"]},
            )

        self.assertTrue(result["result"])
        fake_model.objects.filter.assert_called_once_with(team__contains=42)


if __name__ == "__main__":
    unittest.main()
