import pytest
from django.utils import timezone

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event
from apps.alerts.utils.queryset import iter_queryset_in_pk_batches


@pytest.mark.django_db
def test_pk_cursor_batching_never_materializes_more_than_batch_size():
    source = AlertSource.objects.create(
        name="src", source_id="batch-src", source_type="restful", secret="x"
    )
    Event.objects.bulk_create(
        [
            Event(
                source=source,
                event_id=f"E-{index}",
                title="t",
                level="0",
                raw_data={},
                start_time=timezone.now(),
            )
            for index in range(5)
        ]
    )

    batches = list(iter_queryset_in_pk_batches(Event.objects.order_by("pk"), batch_size=2))

    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert [event.event_id for batch in batches for event in batch] == [
        "E-0", "E-1", "E-2", "E-3", "E-4"
    ]
