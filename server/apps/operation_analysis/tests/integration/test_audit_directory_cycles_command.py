"""目录循环审计命令的数据库集成契约。"""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.operation_analysis.models.models import Directory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_audit_directory_cycles_is_read_only_and_repeatable():
    first = Directory.objects.create(name="审计目录一", groups=[1])
    second = Directory.objects.create(name="审计目录二", groups=[1], parent=first)
    Directory.objects.filter(pk=first.pk).update(parent=second)
    parents_before = list(Directory.objects.order_by("pk").values_list("pk", "parent_id"))

    first_output = StringIO()
    second_output = StringIO()
    call_command("audit_directory_cycles", stdout=first_output)
    call_command("audit_directory_cycles", stdout=second_output)

    assert first_output.getvalue() == second_output.getvalue()
    assert f"发现目录循环: {first.pk} -> {second.pk}" in first_output.getvalue()
    assert list(Directory.objects.order_by("pk").values_list("pk", "parent_id")) == parents_before
