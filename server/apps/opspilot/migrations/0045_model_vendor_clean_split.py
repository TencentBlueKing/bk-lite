import django.db.models.deletion
from django.db import migrations, models


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
    ]
