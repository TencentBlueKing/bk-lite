"""Early pytest plugin to configure environment before Django setup.

Registered as a pytest11 entry point in pyproject.toml.
This ensures INSTALL_APPS is set before pytest-django calls django.setup(),
excluding apps with heavy optional dependencies (e.g., mlops requires mlflow).
Also patches django_minio_backend to avoid connecting to MinIO during tests.
"""
import os

os.environ.setdefault(
    "INSTALL_APPS",
    "system_mgmt,alerts,console_mgmt,job_mgmt,log,"
    "monitor,node_mgmt,operation_analysis,opspilot,cmdb,apm",
)

# Prevent django_minio_backend.apps.ready() from calling
# call_command('initialize_buckets') which connects to MinIO.
# We hook into django.apps.AppConfig.ready via import-time patching:
# override the management module's call_command before django.setup() runs.
_original_call_command = None


def _noop_initialize_buckets(name, *args, **kwargs):
    if name == "initialize_buckets":
        return
    return _original_call_command(name, *args, **kwargs)


def pytest_configure(config):
    """Patch call_command before django.setup() to skip MinIO initialization."""
    global _original_call_command
    import django.core.management as mgmt
    _original_call_command = mgmt.call_command
    mgmt.call_command = _noop_initialize_buckets
