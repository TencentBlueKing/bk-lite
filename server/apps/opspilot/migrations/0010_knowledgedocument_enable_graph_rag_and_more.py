# Generated by Django 4.2.15 on 2025-07-08 09:51

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0009_knowledgegraph_graphchunkmap"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgedocument",
            name="enable_graph_rag",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="enable_naive_rag",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="enable_qa_rag",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="graph_size",
            field=models.IntegerField(default=50, verbose_name="Graph size"),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="qa_size",
            field=models.IntegerField(default=50, verbose_name="QA size"),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="rag_size",
            field=models.IntegerField(default=50, verbose_name="RAG size"),
        ),
    ]
