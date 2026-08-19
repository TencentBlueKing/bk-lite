import pytest

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.utils.k8s_image_registry import DEFAULT_K8S_IMAGE_REGISTRY_PREFIX, build_kubectl_install_command, normalize_k8s_image_registry_prefix


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, DEFAULT_K8S_IMAGE_REGISTRY_PREFIX),
        ("", DEFAULT_K8S_IMAGE_REGISTRY_PREFIX),
        ("harbor.internal.example/observability", "harbor.internal.example/observability"),
        ("10.0.0.8:5000/platform/bklite", "10.0.0.8:5000/platform/bklite"),
        ("[fd00::8]:5000/platform/bklite", "[fd00::8]:5000/platform/bklite"),
    ],
)
def test_normalize_image_registry_prefix_accepts_supported_formats(value, expected):
    assert normalize_k8s_image_registry_prefix(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://harbor.example/bklite",
        "harbor.example/bklite/",
        "harbor.example",
        "harbor.example/BKLite",
        "harbor.example/bklite\nimage: evil",
        'harbor.example/bklite"}}',
        "harbor.example/bklite;curl",
        "harbor.example/{{template}}",
        "harbor.example:70000/bklite",
        123,
    ],
)
def test_normalize_image_registry_prefix_rejects_injection_and_invalid_formats(value):
    with pytest.raises(ValidationAppException):
        normalize_k8s_image_registry_prefix(value)


def test_build_install_command_uses_json_and_shell_safe_serialization():
    command = build_kubectl_install_command("https://node.example/render/?a='b", "token-'-$HOME")

    assert "'\"'\"'" in command
    assert "$HOME" in command
    assert command.endswith("| kubectl apply -f -")
