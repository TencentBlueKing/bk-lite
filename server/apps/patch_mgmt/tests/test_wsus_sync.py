"""WSUS 同步服务单元测试。

通过 mock winrm.Session 验证：
- WsusClient URL 解析
- check_connection 成功/失败
- get_approved_updates JSON 解析
- sync_wsus 入库逻辑
"""

import json

import pytest

from apps.patch_mgmt.constants import OSType, PackageStatus, PatchSourceType, PatchType
from apps.patch_mgmt.models import Patch, PatchSource, WindowsPatchDetail
from apps.patch_mgmt.services import wsus_sync
from apps.patch_mgmt.services.source_sync_service import SourceSyncService
from apps.patch_mgmt.services.wsus_sync import WsusClient, WsusSyncError, WsusUpdate, sync_wsus


def _make_source(**kwargs):
    defaults = {
        "name": "test-wsus",
        "source_type": PatchSourceType.WSUS,
        "url": "http://10.10.90.120:8530",
        "auth_user": "cwadmin",
        "auth_password": "secret",
        "team": [1],
    }
    defaults.update(kwargs)
    return PatchSource.objects.create(**defaults)


@pytest.mark.django_db
class TestWsusClientParseUrl:
    def test_parse_url_with_port(self):
        source = _make_source(url="http://10.10.90.120:8530")
        client = WsusClient(source)
        assert client.host == "10.10.90.120"
        assert client.wsus_port == 8530

    def test_parse_url_https(self):
        source = _make_source(url="https://10.10.90.120:8531")
        client = WsusClient(source)
        assert client.host == "10.10.90.120"
        assert client.wsus_port == 8531

    def test_parse_url_default_port(self):
        source = _make_source(url="http://10.10.90.120")
        client = WsusClient(source)
        assert client.host == "10.10.90.120"
        assert client.wsus_port == 8530

    def test_parse_url_no_scheme(self):
        source = _make_source(url="10.10.90.120:8530")
        client = WsusClient(source)
        assert client.host == "10.10.90.120"
        assert client.wsus_port == 8530

    def test_parse_url_empty_raises(self):
        source = _make_source(url="")
        with pytest.raises(WsusSyncError, match="未配置 URL"):
            WsusClient(source)

    def test_winrm_endpoint(self):
        source = _make_source(url="http://10.10.90.120:8530")
        client = WsusClient(source)
        assert client.winrm_url == "http://10.10.90.120:5985/wsman"


class _FakeResult:
    def __init__(self, status_code=0, stdout="", stderr=""):
        self.status_code = status_code
        self.std_out = stdout.encode("utf-8")
        self.std_err = stderr.encode("utf-8")


@pytest.mark.django_db
class TestWsusClientCheckConnection:
    def test_check_connection_success(self, monkeypatch):
        source = _make_source()
        client = WsusClient(source)

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout="OK"),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        assert client.check_connection() is True

    def test_check_connection_error(self, monkeypatch):
        source = _make_source()
        client = WsusClient(source)

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout="ERROR: 连接失败"),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        assert client.check_connection() is False

    def test_check_connection_winrm_exception(self, monkeypatch):
        source = _make_source()
        client = WsusClient(source)

        def raise_session(*a, **kw):
            raise Exception("Connection refused")

        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": raise_session,
        }))

        assert client.check_connection() is False


@pytest.mark.django_db
class TestWsusClientGetApprovedUpdates:
    def test_get_updates_parses_json(self, monkeypatch):
        source = _make_source()
        client = WsusClient(source)

        json_data = json.dumps([
            {
                "UpdateId": "abc-123",
                "Title": "2025-11 Security Update (KB5072653)",
                "KbNumber": "5072653",
                "Classification": "Security Updates",
                "Severity": "Critical",
                "Products": ["Windows 10", "Windows 11"],
                "SecurityBulletins": ["MS25-001"],
                "Description": "A security update",
                "ArrivalDate": "2025-11-10T00:00:00",
            },
        ])

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout=json_data),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        updates = client.get_approved_updates()
        assert len(updates) == 1
        u = updates[0]
        assert u.update_id == "abc-123"
        assert u.title == "2025-11 Security Update (KB5072653)"
        assert u.kb_number == "5072653"
        assert u.classification == "Security Updates"
        assert u.severity == "Critical"
        assert u.products == ["Windows 10", "Windows 11"]
        assert u.security_bulletins == ["MS25-001"]

    def test_get_updates_empty(self, monkeypatch):
        source = _make_source()
        client = WsusClient(source)

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout="[]"),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        updates = client.get_approved_updates()
        assert updates == []

    def test_get_updates_kb_from_title(self, monkeypatch):
        source = _make_source()
        client = WsusClient(source)

        json_data = json.dumps([
            {
                "UpdateId": "abc-456",
                "Title": "Cumulative Update KB5034441",
                "KbNumber": None,
                "Classification": "Updates",
                "Severity": "Unspecified",
                "Products": [],
                "SecurityBulletins": [],
                "Description": "",
                "ArrivalDate": "",
            },
        ])

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout=json_data),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        updates = client.get_approved_updates()
        assert len(updates) == 1
        assert updates[0].kb_number == "KB5034441"

    def test_get_updates_invalid_json_raises(self, monkeypatch):
        source = _make_source()
        client = WsusClient(source)

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout="not json"),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        with pytest.raises(WsusSyncError, match="JSON 解析失败"):
            client.get_approved_updates()


@pytest.mark.django_db
class TestSyncWsus:
    def test_sync_no_updates_returns_zero(self, monkeypatch):
        source = _make_source()

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout="[]"),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        result = sync_wsus(source)
        assert result == {"total": 0, "created": 0, "updated": 0, "skipped": 0}

    def test_sync_creates_patches(self, monkeypatch):
        source = _make_source()

        json_data = json.dumps([
            {
                "UpdateId": "uid-1",
                "Title": "Security Update KB5072653",
                "KbNumber": "5072653",
                "Classification": "Security Updates",
                "Severity": "Critical",
                "Products": ["Windows 10"],
                "SecurityBulletins": ["MS25-9999"],
                "Description": "desc",
                "ArrivalDate": "2025-11-10T00:00:00",
            },
            {
                "UpdateId": "uid-2",
                "Title": "Update KB5034441",
                "KbNumber": "5034441",
                "Classification": "Updates",
                "Severity": "Important",
                "Products": ["Windows 11"],
                "SecurityBulletins": [],
                "Description": "",
                "ArrivalDate": "",
            },
        ])

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout=json_data),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        result = sync_wsus(source)
        assert result["total"] == 2
        assert result["created"] == 2
        assert result["updated"] == 0

        patches = Patch.objects.filter(os_type=OSType.WINDOWS)
        assert patches.count() == 2

        p1 = patches.get(title="5072653")
        assert p1.severity == "critical"
        assert p1.cve_list == []
        assert p1.pkg_status == PackageStatus.READY
        assert p1.sources.filter(id=source.id).exists()

        detail1 = WindowsPatchDetail.objects.get(patch=p1)
        assert detail1.kb_number == "KB5072653"
        assert detail1.product_list == ["Windows 10"]
        assert detail1.ms_bulletin == "MS25-9999"

    def test_sync_updates_existing_patch(self, monkeypatch):
        source = _make_source()
        # 预创建一个 patch
        Patch.objects.create(
            title="5072653", os_type=OSType.WINDOWS,
            patch_type=PatchType.SECURITY, severity="unspecified",
            pkg_status=PackageStatus.PENDING,
        )

        json_data = json.dumps([
            {
                "UpdateId": "uid-1",
                "Title": "Security Update KB5072653",
                "KbNumber": "5072653",
                "Classification": "Security Updates",
                "Severity": "Critical",
                "Products": ["Windows 10"],
                "SecurityBulletins": [],
                "Description": "",
                "ArrivalDate": "",
            },
        ])

        fake_session = type("FakeSession", (), {
            "run_ps": lambda self, script: _FakeResult(stdout=json_data),
        })
        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": lambda *a, **kw: fake_session(),
        }))

        result = sync_wsus(source)
        assert result["created"] == 0
        assert result["updated"] == 1

        p = Patch.objects.get(title="5072653")
        assert p.severity == "critical"
        assert p.pkg_status == PackageStatus.READY
        assert p.sources.filter(id=source.id).exists()

    def test_sync_skips_manual_package_with_same_kb(self, monkeypatch):
        source = _make_source()
        manual = Patch.objects.create(
            title="Manual KB5072653",
            os_type=OSType.WINDOWS,
            patch_type=PatchType.SECURITY,
            severity="important",
            pkg_status=PackageStatus.READY,
        )
        WindowsPatchDetail.objects.create(
            patch=manual,
            kb_number="KB5072653",
            package_file="windows/1/manual.msu",
        )
        monkeypatch.setattr(
            WsusClient,
            "get_approved_updates",
            lambda self: [WsusUpdate(
                update_id="uid-manual-conflict",
                title="Security Update KB5072653",
                kb_number="5072653",
                classification="Security Updates",
                severity="Critical",
                products=["Windows 10"],
                security_bulletins=[],
                description="",
                arrival_date="",
            )],
        )

        result = sync_wsus(source)

        manual.refresh_from_db()
        assert result["skipped"] == 1
        assert manual.title == "Manual KB5072653"
        assert manual.severity == "important"
        assert not manual.sources.filter(id=source.id).exists()

    def test_sync_matches_existing_synced_patch_by_normalized_kb(self, monkeypatch):
        source = _make_source()
        existing = Patch.objects.create(
            title="Old WSUS title",
            os_type=OSType.WINDOWS,
            pkg_status=PackageStatus.READY,
        )
        WindowsPatchDetail.objects.create(patch=existing, kb_number="KB5072653")
        monkeypatch.setattr(
            WsusClient,
            "get_approved_updates",
            lambda self: [WsusUpdate(
                update_id="uid-existing",
                title="New title",
                kb_number="5072653",
                classification="Security Updates",
                severity="Critical",
                products=["Windows 11"],
                security_bulletins=[],
                description="",
                arrival_date="",
            )],
        )

        result = sync_wsus(source)

        assert result["created"] == 0
        assert result["updated"] == 1
        assert Patch.objects.filter(os_type=OSType.WINDOWS).count() == 1
        assert existing.sources.filter(id=source.id).exists()

    def test_ingest_selected_marks_patch_ready(self, monkeypatch):
        source = _make_source()
        update = WsusUpdate(
            update_id="uid-ready",
            title="Security Update KB5072654",
            kb_number="5072654",
            classification="Security Updates",
            severity="Important",
            products=["Windows 11"],
            security_bulletins=[],
            description="",
            arrival_date="",
        )
        monkeypatch.setattr(WsusClient, "get_approved_updates", lambda self: [update])

        result = SourceSyncService.ingest_selected(source, ["uid-ready"])

        assert result["created"] == 1
        assert Patch.objects.get(title="5072654").pkg_status == PackageStatus.READY

    def test_sync_winrm_failure_raises(self, monkeypatch):
        source = _make_source()

        def raise_session(*a, **kw):
            raise Exception("Connection refused")

        monkeypatch.setattr(wsus_sync, "winrm", type("FakeWinRM", (), {
            "Session": raise_session,
        }))

        with pytest.raises(WsusSyncError, match="WinRM 连接失败"):
            sync_wsus(source)
