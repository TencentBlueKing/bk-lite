from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.alerts.models.itsm import AlertItsmIntegration


def run(origin="https://10.11.10.182"):
    with patch("apps.alerts.management.commands.init_itsm_integration.default_public_origin", return_value=origin):
        call_command("init_itsm_integration")


@pytest.mark.django_db
def test_seeds_disabled_integration_with_default_url():
    run("https://10.11.10.182/")

    instance = AlertItsmIntegration.objects.get(team_id=1)
    assert (instance.name, instance.enabled, instance.encrypted_token) == ("ITSM", False, "")
    assert instance.config == {"url": "https://10.11.10.182/openapi/v1/itsm/openapi/v1", "ca_pem": "", "failure_notification": {}}


@pytest.mark.django_db
def test_keeps_existing_integration():
    AlertItsmIntegration.objects.create(team_id=1, name="现网", enabled=True, config={"url": "https://other/api"}, encrypted_token="x")

    run()

    instance = AlertItsmIntegration.objects.get(team_id=1)
    assert (instance.name, instance.enabled, instance.config["url"]) == ("现网", True, "https://other/api")
