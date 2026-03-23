import django.db.models.deletion
from django.db import migrations, models

PLACEHOLDER_API_KEY = "your_openai_api_key"


def _is_placeholder(config, keys):
    if not isinstance(config, dict):
        return False
    return any(config.get(key) == PLACEHOLDER_API_KEY for key in keys)


def _encrypt_vendor_api_key(vendor, EncryptMixin):
    vendor_data = {"api_key": vendor.api_key or ""}
    EncryptMixin.encrypt_field(vendor, "api_key", vendor_data)
    vendor.api_key = vendor_data["api_key"]
    return vendor


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
            index=0,
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
                "api_key": config.get("openai_api_key", ""),
                "team": obj.team or [],
                "enabled": obj.enabled,
            }
        )
    if delete_ids:
        LLMModel.objects.filter(id__in=delete_ids).delete()
    if not keep_models:
        return
    from apps.core.mixinx import EncryptMixin as EncryptMixinClass

    created_vendors = _bulk_create_vendors(ModelVendor, EncryptMixinClass, vendor_specs)
    updated_models = _bulk_assign_models(keep_models, created_vendors, lambda obj: (obj.llm_config or {}).get("model") or obj.name)
    LLMModel.objects.bulk_update(updated_models, ["vendor", "model"], batch_size=500)


def _migrate_provider_model(apps, model_name, config_field, api_base_key="base_url", api_key_key="api_key"):
    ModelVendor = apps.get_model("opspilot", "ModelVendor")
    ProviderModel = apps.get_model("opspilot", model_name)
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
                "api_key": config.get(api_key_key, ""),
                "team": obj.team or [],
                "enabled": obj.enabled,
            }
        )
    if delete_ids:
        ProviderModel.objects.filter(id__in=delete_ids).delete()
    if not keep_models:
        return
    from apps.core.mixinx import EncryptMixin as EncryptMixinClass

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
        ("opspilot", "0044_workflowconversationhistory_execution_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelVendor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="名称")),
                (
                    "vendor_type",
                    models.CharField(
                        choices=[
                            ("openai", "OpenAI"),
                            ("azure", "Azure"),
                            ("aliyun", "阿里云"),
                            ("zhipu", "智谱"),
                            ("baidu", "百度"),
                            ("anthropic", "Anthropic"),
                            ("deepseek", "DeepSeek"),
                            ("other", "其它"),
                        ],
                        default="openai",
                        max_length=50,
                        verbose_name="供应商类型",
                    ),
                ),
                ("api_base", models.CharField(blank=True, default="", max_length=500, verbose_name="API地址")),
                ("api_key", models.TextField(blank=True, default="", verbose_name="API Key")),
                ("enabled", models.BooleanField(default=True, verbose_name="是否启用")),
                ("team", models.JSONField(default=list, verbose_name="组织")),
                ("description", models.TextField(blank=True, default="", null=True, verbose_name="简介")),
                ("is_build_in", models.BooleanField(default=False)),
                ("index", models.IntegerField(default=0, verbose_name="排序")),
            ],
            options={"verbose_name": "供应商", "verbose_name_plural": "供应商", "db_table": "opspilot_modelvendor"},
        ),
        migrations.AddField(
            model_name="embedprovider", name="model", field=models.CharField(blank=True, max_length=255, null=True, verbose_name="模型")
        ),
        migrations.AddField(model_name="llmmodel", name="model", field=models.CharField(blank=True, max_length=255, null=True, verbose_name="模型")),
        migrations.AddField(model_name="ocrprovider", name="model", field=models.CharField(blank=True, max_length=255, null=True, verbose_name="模型")),
        migrations.AddField(
            model_name="rerankprovider", name="model", field=models.CharField(blank=True, max_length=255, null=True, verbose_name="模型")
        ),
        migrations.AddField(
            model_name="embedprovider",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="embed_models",
                to="opspilot.modelvendor",
                verbose_name="供应商",
            ),
        ),
        migrations.AddField(
            model_name="llmmodel",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="llm_models",
                to="opspilot.modelvendor",
                verbose_name="供应商",
            ),
        ),
        migrations.AddField(
            model_name="ocrprovider",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ocr_models",
                to="opspilot.modelvendor",
                verbose_name="供应商",
            ),
        ),
        migrations.AddField(
            model_name="rerankprovider",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rerank_models",
                to="opspilot.modelvendor",
                verbose_name="供应商",
            ),
        ),
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
    ]
