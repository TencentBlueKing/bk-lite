"""NATS-Executor / Ansible-Executor 作为托管组件暴露。"""
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.management.services.node_init.collector_init import import_collector
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.views.collector import CollectorViewSet


def _build_admin_user():
    return User(
        username="executor-component-user",
        domain="domain.com",
        locale="en",
        is_superuser=True,
        roles=["admin"],
        group_list=[{"id": 1, "name": "Team"}],
    )


def _create_collector(**overrides):
    defaults = {
        "service_type": "exec",
        "node_operating_system": NodeConstants.LINUX_OS,
        "cpu_architecture": NodeConstants.X86_64_ARCH,
        "executable_path": "/opt/fusion-collectors/bin/nats-executor",
        "execute_parameters": "--config %s",
        "introduction": "executor",
        "icon": "caijixinxi",
        "default_config": {},
        "tags": ["executor", NodeConstants.LINUX_OS, NodeConstants.X86_64_ARCH],
        "package_name": "nats-executor",
        "created_by": "tester",
        "updated_by": "tester",
    }
    defaults.update(overrides)
    return Collector.objects.create(**defaults)


@pytest.mark.django_db
def test_collector_list_includes_nats_and_ansible_executors(monkeypatch):
    monkeypatch.setattr(
        "apps.node_mgmt.views.collector.LanguageLoader",
        lambda *args, **kwargs: SimpleNamespace(get=lambda key: None),
    )
    _create_collector(id="natsexecutor_linux", name="NATS-Executor")
    _create_collector(
        id="ansibleexecutor_linux",
        name="Ansible-Executor",
        executable_path="/opt/fusion-collectors/bin/ansible-executor",
        package_name="ansible-executor",
    )
    _create_collector(
        id="telegraf_linux",
        name="Telegraf",
        tags=["monitor", NodeConstants.LINUX_OS, NodeConstants.X86_64_ARCH],
        executable_path="/opt/fusion-collectors/bin/telegraf",
        package_name="telegraf",
    )

    factory = APIRequestFactory()
    view = CollectorViewSet.as_view({"get": "list"})
    request = factory.get("/node_mgmt/api/collector/")
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 200
    assert {item["id"] for item in response.data} == {
        "natsexecutor_linux",
        "ansibleexecutor_linux",
        "telegraf_linux",
    }
    assert CollectorConstants.IGNORE_COLLECTORS == []


@pytest.mark.django_db
def test_executor_tag_filter_returns_hosted_executors(monkeypatch):
    monkeypatch.setattr(
        "apps.node_mgmt.views.collector.LanguageLoader",
        lambda *args, **kwargs: SimpleNamespace(get=lambda key: None),
    )
    _create_collector(id="natsexecutor_linux", name="NATS-Executor")
    _create_collector(
        id="telegraf_linux",
        name="Telegraf",
        tags=["monitor", NodeConstants.LINUX_OS, NodeConstants.X86_64_ARCH],
        executable_path="/opt/fusion-collectors/bin/telegraf",
        package_name="telegraf",
    )

    factory = APIRequestFactory()
    view = CollectorViewSet.as_view({"get": "list"})
    request = factory.get("/node_mgmt/api/collector/", {"tags": "executor"})
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 200
    assert [item["id"] for item in response.data] == ["natsexecutor_linux"]


@pytest.mark.django_db
def test_import_collector_writes_executor_app_tag():
    import_collector(
        [
            {
                "id": "natsexecutor_linux",
                "name": "NATS-Executor",
                "service_type": "exec",
                "node_operating_system": NodeConstants.LINUX_OS,
                "cpu_architecture": NodeConstants.X86_64_ARCH,
                "executable_path": "/opt/fusion-collectors/bin/nats-executor",
                "execute_parameters": "--config %s",
                "validation_parameters": "",
                "default_template": "",
                "introduction": "NATS Executor",
                "icon": "caijixinxi",
                "controller_default_run": True,
                "default_config": {},
                "tags": ["executor", "linux", "x86_64"],
                "package_name": "nats-executor",
            }
        ]
    )

    collector = Collector.objects.get(id="natsexecutor_linux")
    assert "executor" in collector.tags
    assert CollectorConstants.TAG_ENUM["executor"]["is_app"] is True
