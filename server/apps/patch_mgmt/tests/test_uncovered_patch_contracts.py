"""补齐补丁评估、连通性和序列化展示中原先遗漏的公共契约。"""

import io
from types import SimpleNamespace

import pytest
from rest_framework import serializers

from apps.patch_mgmt.constants import OSType, PatchSourceType
from apps.patch_mgmt.serializers.baseline import (
    BaselineRequirementSerializer,
    PatchBaselineListSerializer,
)
from apps.patch_mgmt.serializers.patch_source import (
    PatchSourceSerializer,
    infer_distro_name,
)
from apps.patch_mgmt.services import assess_parsers, target_connectivity
from apps.patch_mgmt.services.target_execution_route import (
    TargetExecutionRoute,
    TargetExecutorUnavailable,
    TargetTransport,
)


pytestmark = pytest.mark.unit


def _serializer_without_database_init(serializer_class):
    serializer = serializer_class.__new__(serializer_class)
    serializer._context = {}
    return serializer


def test_wua_parser_filters_noise_and_normalizes_embedded_kb_numbers():
    stdout = """
    ignored line
    ||
    |Important|missing kb
    prefix KB5040430 suffix|Important|Cumulative|title suffix
    invalid|Low|No KB
    kb1234567|Critical|Security Update
    """
    assert assess_parsers.parse_wua_search(stdout) == {
        "KB5040430": {
            "severity": "Important",
            "title": "Cumulative|title suffix",
        },
        "KB1234567": {
            "severity": "Critical",
            "title": "Security Update",
        },
    }


@pytest.mark.parametrize(
    ("severity", "existing", "expected", "save_count"),
    [
        ("", "unspecified", "unspecified", 0),
        ("Unknown", "unspecified", "unspecified", 0),
        ("Critical", "critical", "critical", 0),
        ("Critical", "important", "important", 0),
        (" Important ", "unspecified", "important", 1),
    ],
)
def test_wua_severity_backfill_only_enriches_unspecified_patch(
    severity, existing, expected, save_count
):
    saved = []
    patch = SimpleNamespace(
        id=7,
        severity=existing,
        save=lambda **kwargs: saved.append(kwargs),
    )
    assess_parsers._backfill_patch_severity(patch, severity)
    assert patch.severity == expected
    assert len(saved) == save_count
    if saved:
        assert saved == [{"update_fields": ["severity", "updated_at"]}]


def test_linux_assessment_reports_missing_detail_and_empty_package_name():
    requirements = [
        SimpleNamespace(id=1, patch=SimpleNamespace()),
        SimpleNamespace(
            id=2,
            patch=SimpleNamespace(
                linux_detail=SimpleNamespace(pkg_name="")
            ),
        ),
    ]
    result = assess_parsers.assess_linux_requirements("", requirements)
    assert result[1].evidence == {"error": "missing linux_detail"}
    assert result[1].satisfied is False
    assert result[2].reason == "补丁未配置包名"


def test_windows_combined_assessment_covers_missing_empty_and_installable_kbs():
    saved = []
    installable_patch = SimpleNamespace(
        id=3,
        severity="unspecified",
        windows_detail=SimpleNamespace(kb_number="kb5040430"),
        save=lambda **kwargs: saved.append(kwargs),
    )
    requirements = [
        SimpleNamespace(id=1, patch=SimpleNamespace()),
        SimpleNamespace(
            id=2,
            patch=SimpleNamespace(
                windows_detail=SimpleNamespace(kb_number="")
            ),
        ),
        SimpleNamespace(id=3, patch=installable_patch),
    ]
    stdout = (
        "KB5040430|Important|Cumulative Update\n"
        "===HOTFIX===\nKB5000000\n"
    )

    result = assess_parsers.assess_windows_requirements(stdout, requirements)

    assert result[1].evidence == {"error": "missing windows_detail"}
    assert result[2].reason == "补丁未配置 KB 号"
    assert result[3].satisfied is False
    assert result[3].evidence["severity"] == "Important"
    assert installable_patch.severity == "important"
    assert saved == [{"update_fields": ["severity", "updated_at"]}]


def test_windows_pure_wua_format_marks_update_as_missing():
    patch = SimpleNamespace(
        id=3,
        severity="important",
        windows_detail=SimpleNamespace(kb_number="KB5040430"),
        save=pytest.fail,
    )
    result = assess_parsers.assess_windows_requirements(
        "KB5040430|Important|Cumulative Update",
        [SimpleNamespace(id=3, patch=patch)],
    )
    assert result[3].reason == "KB5040430 适用但未安装"
    assert result[3].evidence["installed_kbs"] == []


def test_probe_rejects_unsupported_os_with_structured_routing_failure():
    result = target_connectivity.probe_target_data(
        {
            "ip": "10.0.0.8",
            "os_type": "aix",
        }
    )

    assert result.reachable is False
    assert result.port is None
    assert result.transport == "unknown"
    assert result.stage == "routing"
    assert result.reason_code == "invalid_configuration"
    assert "aix" in result.detail


def test_private_key_reader_rewinds_binary_stream_and_accepts_text():
    source = io.BytesIO(b"-----BEGIN PRIVATE KEY-----")
    source.read()

    assert target_connectivity._read_private_key(source) == (
        "-----BEGIN PRIVATE KEY-----"
    )
    assert target_connectivity._read_private_key("inline-key") == "inline-key"
    assert target_connectivity._read_private_key(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            {"result": {"exit_code": 0, "stdout": "ok"}, "task_id": "7"},
            {
                "result": {"exit_code": 0, "stdout": "ok"},
                "exit_code": 0,
                "stdout": "ok",
                "task_id": "7",
            },
        ),
        (
            {"result": "patch-connectivity-ok", "exit_code": 0},
            {
                "result": "patch-connectivity-ok",
                "stdout": "patch-connectivity-ok",
                "exit_code": 0,
            },
        ),
        ("plain output", {"exit_code": 0, "stdout": "plain output"}),
        (None, {"exit_code": 0, "stdout": ""}),
    ],
)
def test_probe_result_normalization_handles_executor_response_shapes(
    raw, expected
):
    assert target_connectivity._normalize_result(raw) == expected


@pytest.mark.parametrize(
    ("error", "expected_stage", "expected_reason"),
    [
        (TimeoutError("request timeout"), "command", "connection_timeout"),
        (
            TargetExecutorUnavailable("offline"),
            "routing",
            "executor_unavailable",
        ),
        (
            RuntimeError("permission denied"),
            "authentication",
            "authentication_failed",
        ),
    ],
)
def test_probe_failure_classification_is_actionable_and_redacts_secrets(
    error, expected_stage, expected_reason
):
    route = TargetExecutionRoute(
        TargetTransport.NATS_SSH,
        "regional-executor",
        2222,
    )
    if expected_reason == "authentication_failed":
        error = RuntimeError("password=super-secret permission denied")

    result = target_connectivity._failure_result(error, route)

    assert result.reachable is False
    assert result.stage == expected_stage
    assert result.reason_code == expected_reason
    assert result.transport == TargetTransport.NATS_SSH
    assert result.port == 2222
    assert "super-secret" not in result.detail


@pytest.mark.parametrize(
    ("source_type", "url", "expected"),
    [
        (PatchSourceType.WSUS, "https://wsus.example", "Windows Server"),
        (PatchSourceType.YUM_REPO, "https://mirror/rocky/9", "Rocky Linux"),
        (PatchSourceType.YUM_REPO, "https://mirror/centos/8", "CentOS"),
        (PatchSourceType.YUM_REPO, "https://mirror/redhat/9", "RHEL"),
        (PatchSourceType.DNF_REPO, "https://mirror/rocky/9", "Rocky Linux"),
        (
            PatchSourceType.DNF_REPO,
            "https://mirror/centos-stream/9",
            "CentOS Stream",
        ),
        (PatchSourceType.DNF_REPO, "https://mirror/rhel/9", "RHEL"),
        (PatchSourceType.APT_REPO, "https://archive.ubuntu.com", "Ubuntu"),
        (PatchSourceType.APT_REPO, "https://deb.debian.org", "Debian"),
        (PatchSourceType.APT_REPO, "https://mirror.example", ""),
        ("unsupported", "https://mirror.example", ""),
    ],
)
def test_patch_source_distribution_inference(source_type, url, expected):
    assert infer_distro_name(source_type, url) == expected


def test_requirement_serializer_handles_missing_details_and_fallbacks():
    serializer = BaselineRequirementSerializer()
    missing_windows = SimpleNamespace(
        condition="",
        patch=SimpleNamespace(os_type="windows"),
    )
    assert serializer.get_patch_kb_number(missing_windows) is None
    assert serializer.get_patch_version(missing_windows) == ""
    assert serializer.get_patch_condition(missing_windows) == ""

    linux = SimpleNamespace(
        condition="",
        patch=SimpleNamespace(
            os_type="linux",
            linux_detail=SimpleNamespace(
                pkg_name="openssl",
                pkg_version="3.0.1",
                os_version_range="",
                distro_name="Rocky Linux 9",
                architectures=["x86_64", "aarch64"],
            ),
        ),
    )
    assert serializer.get_patch_version(linux) == "Rocky Linux 9"
    assert serializer.get_patch_arch(linux) == "x86_64, aarch64"
    assert "3.0.1" in serializer.get_patch_condition(linux)


def test_requirement_serializer_prefers_explicit_condition():
    requirement = SimpleNamespace(
        condition="reboot required",
        patch=SimpleNamespace(os_type="linux"),
    )
    assert (
        BaselineRequirementSerializer().get_patch_condition(requirement)
        == "reboot required"
    )


class _RelatedItems:
    def __init__(self, items):
        self.items = list(items)

    def count(self):
        return len(self.items)

    def exists(self):
        return bool(self.items)

    def select_related(self, *_fields):
        return self.items


def test_baseline_list_serializer_reports_counts_architectures_and_assessability(
    monkeypatch,
):
    obj = SimpleNamespace(
        requirements=_RelatedItems(
            [
                SimpleNamespace(
                    patch=SimpleNamespace(
                        os_type="windows",
                        windows_detail=SimpleNamespace(
                            architectures=["x64", "arm64"]
                        ),
                    )
                ),
                SimpleNamespace(
                    patch=SimpleNamespace(
                        os_type="linux",
                        linux_detail=SimpleNamespace(
                            architectures=["x86_64", "arm64"]
                        ),
                    )
                ),
            ]
        ),
        host_bindings=_RelatedItems([SimpleNamespace()]),
    )
    serializer = _serializer_without_database_init(PatchBaselineListSerializer)
    monkeypatch.setattr(serializer, "get_is_assessing", lambda _obj: False)

    assert serializer.get_requirement_count(obj) == 2
    assert serializer.get_bound_host_count(obj) == 1
    assert serializer.get_archs(obj) == ["arm64", "x64", "x86_64"]
    assert serializer.get_can_assess(obj) is True
    assert serializer.get_assess_disabled_reason(obj) == ""


@pytest.mark.parametrize(
    ("requirements", "bindings", "assessing", "reason_fragment"),
    [
        ([], [object()], False, "patch requirements"),
        ([object()], [], False, "bound targets"),
        ([object()], [object()], True, "being assessed"),
    ],
)
def test_baseline_list_serializer_explains_why_assessment_is_disabled(
    monkeypatch, requirements, bindings, assessing, reason_fragment
):
    obj = SimpleNamespace(
        requirements=_RelatedItems(requirements),
        host_bindings=_RelatedItems(bindings),
    )
    serializer = _serializer_without_database_init(PatchBaselineListSerializer)
    monkeypatch.setattr(serializer, "get_is_assessing", lambda _obj: assessing)

    assert serializer.get_can_assess(obj) is False
    assert reason_fragment in serializer.get_assess_disabled_reason(obj)


def test_patch_source_serializer_validates_supported_types_and_infers_distro():
    serializer = _serializer_without_database_init(PatchSourceSerializer)
    assert serializer.validate_source_type(PatchSourceType.APT_REPO) == "apt_repo"
    with pytest.raises(serializers.ValidationError) as exc_info:
        serializer.validate_source_type("local_directory")
    assert "WSUS" in str(exc_info.value)

    attrs = serializer.validate(
        {
            "source_type": PatchSourceType.DNF_REPO,
            "url": "https://mirror.example/rocky/9",
            "distro_name": "",
        }
    )
    assert attrs["distro_name"] == "Rocky Linux"
    assert PatchSourceSerializer.get_has_auth_password(
        SimpleNamespace(auth_password="encrypted")
    )
    assert not PatchSourceSerializer.get_has_auth_password(
        SimpleNamespace(auth_password="")
    )
