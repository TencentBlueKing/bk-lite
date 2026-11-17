"""Real row-lock acceptance tests; SQLite cannot prove these contracts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import connection, connections
from django.utils import timezone

from apps.node_mgmt.models import CloudRegion, EnvironmentInstallAttempt, PackageVersion
from apps.node_mgmt.services.environment_install import EnvironmentInstallService


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("boundary", ["quota", "address"])
def test_postgres_concurrent_reservations_enforce_boundary(boundary):
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL row locks")
    region = CloudRegion.objects.create(name="concurrent-environment")
    package = PackageVersion.objects.create(
        type="controller", object="Controller", os="linux", cpu_architecture="x86_64", version="concurrent-v1", name="controller.zip", sha256="d" * 64
    )

    def grant():
        return EnvironmentInstallService.create(
            owner="installer",
            domain="test",
            team=1,
            cloud_region_id=region.pk,
            package_id=package.pk,
            expires_at=timezone.now() + timedelta(hours=1),
            max_nodes=1,
        )

    first, first_key = grant()
    second, second_key = grant() if boundary == "address" else (first, first_key)
    gate = Barrier(2)

    def reserve(index):
        grant_obj, key = [(first, first_key), (second, second_key)][index]
        connections.close_all()
        try:
            gate.wait(timeout=10)
            return EnvironmentInstallService.reserve(
                grant_id=str(grant_obj.pk),
                installation_key=key,
                request_id=str(uuid4()),
                node_id=str(uuid4()),
                ip="192.0.2.10" if boundary == "address" else f"192.0.2.{10 + index}",
                node_name=f"host-{index}",
                os="linux",
                cpu_architecture="x86_64",
                team=[1],
                user_info={"user": "installer", "domain": "test"},
            )
        except ValueError as error:
            return str(error)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(reserve, (0, 1)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert EnvironmentInstallAttempt.objects.count() == 1
    assert any(boundary in result for result in results if isinstance(result, str))
