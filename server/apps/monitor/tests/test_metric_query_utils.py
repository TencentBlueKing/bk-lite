import pytest

from apps.monitor.tasks.utils.metric_query import format_to_vm_filter


def test_format_to_vm_filter_rejects_structured_label_value():
    with pytest.raises(ValueError) as exc:
        format_to_vm_filter(
            [
                {"name": "service", "method": "=", "value": ["checkout"]},
            ]
        )

    assert "必须是标量" in str(exc.value)
