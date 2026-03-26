from django.db import migrations, models

PLACEHOLDER_API_KEY = "your_openai_api_key"


def _is_placeholder(config, keys):
    if not isinstance(config, dict):
        return False
    return any(config.get(key) == PLACEHOLDER_API_KEY for key in keys)


def _encrypt_vendor_api_key(vendor, EncryptMixin):
    vendor_data = {"api_key": vendor.api_key or ""}
    EncryptMixin.encrypt_field("api_key", vendor_data)
    vendor.api_key = vendor_data["api_key"]
    return vendor


def _normalize_legacy_api_key(api_key, EncryptMixin):
    vendor_data = {"api_key": api_key or ""}
    EncryptMixin.decrypt_field("api_key", vendor_data)
    return vendor_data["api_key"]


def _collect_llm_refs(apps):
    LLMSkill = apps.get_model("opspilot", "LLMSkill")
    QAPairs = apps.get_model("opspilot", "QAPairs")
    KnowledgeGraph = apps.get_model("opspilot", "KnowledgeGraph")
    refs = set(LLMSkill.objects.exclude(llm_model_id=None).values_list("llm_model_id", flat=True))
    refs.update(LLMSkill.objects.exclude(km_llm_model_id=None).values_list("km_llm_model_id", flat=True))
    refs.update(QAPairs.objects.exclude(llm_model_id=None).values_list("llm_model_id", flat=True))
    refs.update(QAPairs.objects.exclude(answer_llm_model_id=None).values_list("answer_llm_model_id", flat=True))
    refs.update(KnowledgeGraph.objects.exclude(llm_model_id=None).values_list("llm_model_id", flat=True))
    return refs


def _collect_provider_refs(apps, model_name):
    refs = set()
    if model_name in {"EmbedProvider", "RerankProvider"}:
        KnowledgeBase = apps.get_model("opspilot", "KnowledgeBase")
        KnowledgeGraph = apps.get_model("opspilot", "KnowledgeGraph")
        field_name = "embed_model_id" if model_name == "EmbedProvider" else "rerank_model_id"
        refs.update(KnowledgeBase.objects.exclude(**{field_name: None}).values_list(field_name, flat=True))
        refs.update(KnowledgeGraph.objects.exclude(**{field_name: None}).values_list(field_name, flat=True))
    if model_name == "OCRProvider":
        KnowledgeDocument = apps.get_model("opspilot", "KnowledgeDocument")
        refs.update(KnowledgeDocument.objects.exclude(ocr_model_id=None).values_list("ocr_model_id", flat=True))
    return refs


def _bulk_create_vendors(ModelVendor, EncryptMixin, vendor_specs):
    vendors = []
    for spec in vendor_specs:
        vendor = ModelVendor(
            name=spec["name"],
            vendor_type=spec["vendor_type"],
            api_base=spec["api_base"],
            api_key=spec["api_key"],
            team=spec["team"],
            enabled=spec["enabled"],
            description="",
            is_build_in=False,
        )
        vendors.append(_encrypt_vendor_api_key(vendor, EncryptMixin))
    return ModelVendor.objects.bulk_create(vendors, batch_size=500)


def _bulk_assign_models(model_objects, created_vendors, model_value_getter):
    for obj, vendor in zip(model_objects, created_vendors):
        obj.vendor_id = vendor.id
        obj.model = model_value_getter(obj)
    return model_objects


def _migrate_llm_model(apps):
    ModelVendor = apps.get_model("opspilot", "ModelVendor")
    LLMModel = apps.get_model("opspilot", "LLMModel")
    from apps.core.mixinx import EncryptMixin as EncryptMixinClass

    llm_refs = _collect_llm_refs(apps)
    keep_models = []
    vendor_specs = []
    delete_ids = []
    for obj in LLMModel.objects.all():
        config = obj.llm_config or {}
        if _is_placeholder(config, ["openai_api_key"]):
            if obj.id not in llm_refs:
                delete_ids.append(obj.id)
                continue
        keep_models.append(obj)
        vendor_specs.append(
            {
                "name": obj.name,
                "vendor_type": "other",
                "api_base": config.get("openai_base_url", ""),
                "api_key": _normalize_legacy_api_key(config.get("openai_api_key", ""), EncryptMixinClass),
                "team": obj.team or [],
                "enabled": obj.enabled,
            }
        )
    if delete_ids:
        LLMModel.objects.filter(id__in=delete_ids).delete()
    if not keep_models:
        return
    created_vendors = _bulk_create_vendors(ModelVendor, EncryptMixinClass, vendor_specs)
    updated_models = _bulk_assign_models(keep_models, created_vendors, lambda obj: (obj.llm_config or {}).get("model") or obj.name)
    LLMModel.objects.bulk_update(updated_models, ["vendor", "model"], batch_size=500)


def _migrate_provider_model(apps, model_name, config_field, api_base_key="base_url", api_key_key="api_key"):
    ModelVendor = apps.get_model("opspilot", "ModelVendor")
    ProviderModel = apps.get_model("opspilot", model_name)
    from apps.core.mixinx import EncryptMixin as EncryptMixinClass

    refs = _collect_provider_refs(apps, model_name)
    keep_models = []
    vendor_specs = []
    delete_ids = []
    for obj in ProviderModel.objects.all():
        config = getattr(obj, config_field) or {}
        if _is_placeholder(config, [api_key_key]):
            if obj.id not in refs:
                delete_ids.append(obj.id)
                continue
        keep_models.append(obj)
        vendor_specs.append(
            {
                "name": obj.name,
                "vendor_type": "other",
                "api_base": config.get(api_base_key, "") or config.get("endpoint", ""),
                "api_key": _normalize_legacy_api_key(config.get(api_key_key, ""), EncryptMixinClass),
                "team": obj.team or [],
                "enabled": obj.enabled,
            }
        )
    if delete_ids:
        ProviderModel.objects.filter(id__in=delete_ids).delete()
    if not keep_models:
        return
    created_vendors = _bulk_create_vendors(ModelVendor, EncryptMixinClass, vendor_specs)
    updated_models = _bulk_assign_models(
        keep_models,
        created_vendors,
        lambda obj: (getattr(obj, config_field) or {}).get("model") or ("" if model_name == "OCRProvider" else obj.name),
    )
    ProviderModel.objects.bulk_update(updated_models, ["vendor", "model"], batch_size=500)


def forward_migrate_vendor_data(apps, schema_editor):
    _migrate_llm_model(apps)
    _migrate_provider_model(apps, "EmbedProvider", "embed_config")
    _migrate_provider_model(apps, "RerankProvider", "rerank_config")
    _migrate_provider_model(apps, "OCRProvider", "ocr_config")


def backward_migrate_vendor_data(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("opspilot", "0045_model_vendor_clean_split"),
    ]

    operations = [
        migrations.RunPython(forward_migrate_vendor_data, backward_migrate_vendor_data),
        migrations.RemoveField(model_name="embedprovider", name="model_type"),
        migrations.RemoveField(model_name="embedprovider", name="embed_config"),
        migrations.RemoveField(model_name="llmmodel", name="model_type"),
        migrations.RemoveField(model_name="llmmodel", name="llm_config"),
        migrations.RemoveField(model_name="ocrprovider", name="model_type"),
        migrations.RemoveField(model_name="ocrprovider", name="ocr_config"),
        migrations.RemoveField(model_name="rerankprovider", name="model_type"),
        migrations.RemoveField(model_name="rerankprovider", name="rerank_config"),
        migrations.DeleteModel(name="ModelType"),
        migrations.CreateModel(
            name="UserPin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(db_index=True, max_length=150, verbose_name="用户名")),
                ("domain", models.CharField(db_index=True, max_length=255, verbose_name="域")),
                (
                    "content_type",
                    models.CharField(choices=[("bot", "工作台"), ("skill", "技能")], db_index=True, max_length=20, verbose_name="内容类型"),
                ),
                ("object_id", models.IntegerField(db_index=True, verbose_name="对象ID")),
            ],
            options={
                "verbose_name": "用户置顶",
                "verbose_name_plural": "用户置顶",
                "db_table": "opspilot_user_pin",
                "indexes": [models.Index(fields=["username", "domain", "content_type"], name="opspilot_us_usernam_54aa63_idx")],
                "unique_together": {("username", "domain", "content_type", "object_id")},
            },
        ),
        migrations.RemoveField(
            model_name="bot",
            name="is_pinned",
        ),
        migrations.RemoveField(
            model_name="llmskill",
            name="is_pinned",
        ),
    ]
