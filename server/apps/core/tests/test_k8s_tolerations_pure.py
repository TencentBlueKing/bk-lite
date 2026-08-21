import pytest

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.utils.k8s_tolerations import apply_k8s_tolerations_param, normalize_k8s_tolerations


def test_normalize_none_means_unset_default():
    assert normalize_k8s_tolerations(None) is None


def test_normalize_empty_list_means_zero_tolerations():
    assert normalize_k8s_tolerations([]) == []


def test_normalize_custom_list_keeps_exists_and_equal():
    assert normalize_k8s_tolerations(
        [
            {"key": "dedicated", "value": "edge", "effect": "NoSchedule"},
            {"key": "CriticalAddonsOnly", "effect": "NoExecute"},
            {"key": "empty-value", "value": "", "effect": "NoSchedule"},
        ]
    ) == [
        {"key": "dedicated", "effect": "NoSchedule", "value": "edge"},
        {"key": "CriticalAddonsOnly", "effect": "NoExecute"},
        {"key": "empty-value", "effect": "NoSchedule", "value": ""},
    ]


@pytest.mark.parametrize(
    "value",
    [
        {"key": "dedicated", "effect": "NoSchedule"},
        "dedicated",
        [{"operator": "Exists", "effect": "NoSchedule"}],
        [{"key": "", "effect": "NoSchedule"}],
        [{"key": 123, "effect": "NoSchedule"}],
        [{"key": "dedicated", "effect": "PreferNoSchedule"}],
        [{"key": "a", "value": "X__DS_TOLERATIONS__X", "effect": "NoSchedule"}],
        [{"key": "X__LOG_VOLUME_MOUNTS__X", "effect": "NoSchedule"}],
        [{"key": "dedicated", "effect": "NoSchedule", "operator": "Equal"}],
        [{"key": "dedicated", "value": 1, "effect": "NoSchedule"}],
        [{"key": "a/b/c", "effect": "NoSchedule"}],
        [{"key": "dedicated"}] * 17,
    ],
)
def test_normalize_rejects_invalid_input(value):
    with pytest.raises(ValidationAppException):
        normalize_k8s_tolerations(value)


def test_apply_omits_unset_and_keeps_empty_list():
    omitted = apply_k8s_tolerations_param({"type": "log"}, None)
    assert "tolerations" not in omitted

    emptied = apply_k8s_tolerations_param({"type": "log"}, [])
    assert emptied["tolerations"] == []

    custom = apply_k8s_tolerations_param(
        {"type": "metric"},
        [{"key": "dedicated", "effect": "NoSchedule"}],
    )
    assert custom["tolerations"] == [{"key": "dedicated", "effect": "NoSchedule"}]
