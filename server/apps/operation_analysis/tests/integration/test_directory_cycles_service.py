"""目录并发重挂的数据库集成测试。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import close_old_connections
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.operation_analysis.models.models import Directory
from apps.operation_analysis.serializers.directory_serializers import DirectoryModelSerializer

pytestmark = pytest.mark.integration


@pytest.mark.django_db(transaction=True, available_apps=["apps.base", "apps.core", "apps.operation_analysis"])
def test_concurrent_cross_reparenting_cannot_persist_cycle():
    first = Directory.objects.create(name="first", groups=[1])
    second = Directory.objects.create(name="second", groups=[1])
    loaded = Barrier(2)

    def reparent(directory_id, parent_id):
        close_old_connections()
        try:
            directory = Directory.objects.get(pk=directory_id)
            parent = Directory.objects.get(pk=parent_id)
            loaded.wait(timeout=5)
            serializer = object.__new__(DirectoryModelSerializer)
            return DirectoryModelSerializer.update(serializer, directory, {"parent": parent})
        except (DjangoValidationError, DRFValidationError) as error:
            return error
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda pair: reparent(*pair),
                [(first.pk, second.pk), (second.pk, first.pk)],
            )
        )

    assert sum(isinstance(result, Directory) for result in results) == 1
    assert sum(isinstance(result, (DjangoValidationError, DRFValidationError)) for result in results) == 1

    first.refresh_from_db()
    second.refresh_from_db()
    assert not (first.parent_id == second.pk and second.parent_id == first.pk)
