from django.db import migrations, models


ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
}


def _normalize(value):
    return ALIASES.get(str(value or "").strip().lower())


def _normalize_list(values, fallback=""):
    normalized = []
    for value in values or []:
        raw = str(value or "").strip()
        item = _normalize(raw)
        if not item and raw.lower() in {"all", "any", "noarch"}:
            item = fallback
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def normalize_cpu_architectures(apps, schema_editor):
    PatchSource = apps.get_model("patch_mgmt", "PatchSource")
    PatchTarget = apps.get_model("patch_mgmt", "PatchTarget")
    WindowsPatchDetail = apps.get_model("patch_mgmt", "WindowsPatchDetail")
    LinuxPatchDetail = apps.get_model("patch_mgmt", "LinuxPatchDetail")

    for source in PatchSource.objects.exclude(arch="").iterator():
        normalized = "" if source.source_type == "wsus" else (_normalize(source.arch) or "")
        if normalized != source.arch:
            source.arch = normalized
            source.save(update_fields=["arch"])

    for target in PatchTarget.objects.exclude(arch="").iterator():
        normalized = _normalize(target.arch) or ""
        if target.os_type == "windows" and normalized != "x86_64":
            normalized = ""
        if normalized != target.arch:
            target.arch = normalized
            target.save(update_fields=["arch"])

    for detail in WindowsPatchDetail.objects.iterator():
        normalized = [
            arch
            for arch in _normalize_list(detail.architectures)
            if arch == "x86_64"
        ] or ["x86_64"]
        if normalized != detail.architectures:
            detail.architectures = normalized
            detail.save(update_fields=["architectures"])

    for detail in LinuxPatchDetail.objects.select_related("patch").iterator():
        source_arch = (
            detail.patch.sources.exclude(arch="")
            .values_list("arch", flat=True)
            .first()
        )
        fallback = _normalize(source_arch) or ""
        normalized = _normalize_list(detail.architectures, fallback=fallback)
        if normalized != detail.architectures:
            detail.architectures = normalized
            detail.save(update_fields=["architectures"])


class Migration(migrations.Migration):
    dependencies = [
        ("patch_mgmt", "0002_governance_record_snapshot"),
    ]

    operations = [
        migrations.RunPython(normalize_cpu_architectures, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="patchsource",
            name="arch",
            field=models.CharField(
                blank=True,
                choices=[("x86_64", "x86_64"), ("arm64", "ARM64")],
                default="",
                max_length=32,
                verbose_name="架构",
            ),
        ),
        migrations.AlterField(
            model_name="patchtarget",
            name="arch",
            field=models.CharField(
                blank=True,
                choices=[("x86_64", "x86_64"), ("arm64", "ARM64")],
                default="",
                max_length=32,
                verbose_name="架构",
            ),
        ),
    ]
