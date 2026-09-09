import pytest
from django.core.management import call_command

from apps.alerts.models.models import Alert


def _alert(alert_id, enrichment):
    return Alert.objects.create(
        alert_id=alert_id,
        fingerprint=f"fp-{alert_id}",
        level="1",
        title="CPU high",
        content="cpu",
        enrichment=enrichment,
    )


@pytest.mark.django_db
def test_normalize_alert_enrichment_supports_dry_run_and_is_idempotent():
    alert = _alert("A-legacy-command", {"cmdb": [{"owner": "alice"}, {"owner": "bob"}]})

    call_command("normalize_alert_enrichment", model="alert", dry_run=True)
    alert.refresh_from_db()
    assert isinstance(alert.enrichment["cmdb"], list)

    call_command("normalize_alert_enrichment", model="alert", batch_size=1)
    alert.refresh_from_db()
    assert alert.enrichment["cmdb"]["owner"] == "alice"
    assert alert.enrichment["cmdb"]["_meta"]["conflicts"] == {"owner": ["bob"]}

    first_result = dict(alert.enrichment)
    call_command("normalize_alert_enrichment", model="alert", batch_size=1)
    alert.refresh_from_db()
    assert alert.enrichment == first_result


@pytest.mark.django_db
def test_normalize_alert_enrichment_can_resume_after_primary_key():
    first = _alert("A-legacy-first", {"cmdb": [{"owner": "first"}]})
    second = _alert("A-legacy-second", {"cmdb": [{"owner": "second"}]})

    call_command(
        "normalize_alert_enrichment",
        model="alert",
        start_after_id=first.pk,
        batch_size=1,
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert isinstance(first.enrichment["cmdb"], list)
    assert second.enrichment == {"cmdb": {"owner": "second"}}
