"""环境安装授权及目标主机的持久幂等记录。"""
import uuid

from django.db import models


class EnvironmentInstallGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.OneToOneField("system_mgmt.SystemAPIToken", on_delete=models.PROTECT)
    owner = models.CharField(max_length=150)
    domain = models.CharField(max_length=100)
    team = models.PositiveIntegerField()
    cloud_region = models.ForeignKey("node_mgmt.CloudRegion", on_delete=models.PROTECT)
    package = models.ForeignKey("node_mgmt.PackageVersion", on_delete=models.PROTECT)
    package_sha256 = models.CharField(max_length=64)
    package_version = models.CharField(max_length=100)
    max_nodes = models.PositiveIntegerField()
    required_components = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class EnvironmentInstallAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grant = models.ForeignKey(EnvironmentInstallGrant, on_delete=models.PROTECT, related_name="attempts")
    request_id = models.UUIDField()
    node_id = models.CharField(max_length=100, unique=True)
    ip = models.GenericIPAddressField(protocol="IPv4")
    node_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    registered_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    failure_stage = models.CharField(max_length=32, blank=True, default="")
    error_code = models.PositiveIntegerField(default=0)
    last_reported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("grant", "request_id"), name="uniq_environment_install_request")]
