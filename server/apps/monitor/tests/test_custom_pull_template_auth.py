from apps.monitor.services.custom_pull_plugin import DEFAULT_PULL_CHILD_TEMPLATE
from apps.monitor.utils.plugin_controller import Controller


def _base_context(**overrides):
    context = {
        "auth_type": "none",
        "config_id": "CONFIG_ID",
        "instance_type": "custom",
        "interval": 60,
        "logical_instance_value": "instance-1",
        "plugin_id": "plugin-1",
        "server_url": "http://127.0.0.1:9090/metrics",
    }
    context.update(overrides)
    return context


def _render(**overrides):
    return Controller({}).render_template(
        DEFAULT_PULL_CHILD_TEMPLATE,
        _base_context(**overrides),
        escape_toml_strings=True,
    )


def test_custom_pull_template_renders_without_optional_auth_variables():
    rendered = _render()

    assert 'urls = ["http://127.0.0.1:9090/metrics"]' in rendered
    assert "username =" not in rendered
    assert "password =" not in rendered
    assert "bearer_token =" not in rendered


def test_custom_pull_template_renders_basic_auth_without_bearer_variable():
    rendered = _render(
        auth_type="basic",
        username="metrics-user",
        ENV_PASSWORD="secret-value",
    )

    assert 'username = "metrics-user"' in rendered
    assert 'password = "${PASSWORD__CONFIG_ID}"' in rendered
    assert "secret-value" not in rendered
    assert "bearer_token =" not in rendered


def test_custom_pull_template_renders_bearer_auth_without_password_variable():
    rendered = _render(
        auth_type="bearer",
        ENV_BEARER_TOKEN="secret-token",
    )

    assert 'bearer_token = "${BEARER_TOKEN__CONFIG_ID}"' in rendered
    assert "secret-token" not in rendered
    assert "password =" not in rendered
