import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0066_alter_chatapplication_unique_together_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PageDirectoryChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("from_assignment_mode", models.CharField(blank=True, choices=[("auto", "Auto"), ("manual", "Manual")], default="", max_length=10)),
                ("to_assignment_mode", models.CharField(choices=[("auto", "Auto"), ("manual", "Manual")], max_length=10)),
                ("source", models.CharField(db_index=True, max_length=30)),
                ("operator", models.CharField(blank=True, default="", max_length=100)),
                ("reason", models.TextField(blank=True, default="")),
            ],
            options={
                "db_table": "opspilot_wiki_page_directory_change",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="WikiDirectory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("key", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("sort_order", models.IntegerField(default=0)),
                (
                    "origin",
                    models.CharField(choices=[("system", "System"), ("schema", "Schema"), ("manual", "Manual")], default="manual", max_length=20),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("retired", "Retired"), ("merged", "Merged"), ("archived", "Archived")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("accepts_pages", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "opspilot_wiki_directory",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="WikiGeneration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("kind", models.CharField(choices=[("build", "Build"), ("governance", "Governance"), ("rollback", "Rollback")], max_length=20)),
                ("structure_fingerprint", models.CharField(db_index=True, max_length=64)),
                ("pipeline_version", models.CharField(max_length=64)),
                ("source_fingerprints", models.JSONField(default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("preparing", "Preparing"),
                            ("ready", "Ready"),
                            ("active", "Active"),
                            ("superseded", "Superseded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="preparing",
                        max_length=20,
                    ),
                ),
            ],
            options={
                "db_table": "opspilot_wiki_generation",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="WikiGenerationIndexEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("title", models.CharField(max_length=255)),
                ("normalized_title", models.CharField(max_length=255)),
                ("aliases", models.JSONField(default=list)),
                ("page_type", models.CharField(default="concept", max_length=50)),
                ("tags", models.JSONField(default=list)),
                ("directory_key", models.CharField(max_length=64)),
                ("directory_breadcrumb", models.JSONField(default=list)),
                ("headings", models.JSONField(default=list)),
                ("keywords", models.JSONField(default=list)),
                ("entities", models.JSONField(default=list)),
                ("summary", models.TextField(blank=True, default="")),
                ("search_text", models.TextField(blank=True, default="")),
                ("content_fingerprint", models.CharField(db_index=True, max_length=64)),
            ],
            options={
                "db_table": "opspilot_wiki_generation_index_entry",
            },
        ),
        migrations.CreateModel(
            name="WikiGenerationOverview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("scope_key", models.CharField(max_length=64)),
                ("deterministic_text", models.TextField(default="")),
                ("semantic_text", models.TextField(blank=True, default="")),
                (
                    "semantic_status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("ready", "Ready"), ("degraded", "Degraded"), ("skipped", "Skipped")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("referenced_page_ids", models.JSONField(default=list)),
                ("content_fingerprint", models.CharField(db_index=True, max_length=64)),
            ],
            options={
                "db_table": "opspilot_wiki_generation_overview",
            },
        ),
        migrations.CreateModel(
            name="WikiGenerationPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("directory_key_snapshot", models.CharField(max_length=64)),
                ("directory_breadcrumb_snapshot", models.JSONField(default=list)),
                ("assignment_mode", models.CharField(choices=[("auto", "Auto"), ("manual", "Manual")], max_length=10)),
                ("page_status", models.CharField(max_length=20)),
                ("page_display_snapshot", models.JSONField(default=dict)),
            ],
            options={
                "db_table": "opspilot_wiki_generation_page",
            },
        ),
        migrations.CreateModel(
            name="WikiImportPreflight",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("actor", models.CharField(max_length=150)),
                ("archive_sha256", models.CharField(db_index=True, max_length=64)),
                ("filename", models.CharField(blank=True, default="", max_length=255)),
                ("archive_kind", models.CharField(max_length=20)),
                ("structure_version", models.PositiveIntegerField(blank=True, null=True)),
                ("options", models.JSONField(default=dict)),
                ("preview", models.JSONField(default=dict)),
                ("preview_fingerprint", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("consumed", "Consumed"), ("expired", "Expired")],
                        db_index=True,
                        default="active",
                        max_length=20,
                    ),
                ),
            ],
            options={
                "db_table": "opspilot_wiki_import_preflight",
            },
        ),
        migrations.CreateModel(
            name="WikiStructureRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("revision_no", models.PositiveIntegerField()),
                ("structure_snapshot", models.JSONField(default=dict)),
                ("fingerprint", models.CharField(db_index=True, max_length=64)),
            ],
            options={
                "db_table": "opspilot_wiki_structure_revision",
                "ordering": ["-revision_no"],
            },
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="activation",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="budget_trace",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="checkpoint",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="directory_trace",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="page_actions",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="pipeline_version",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="source_fingerprints",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="structure_fingerprint",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="knowledgepage",
            name="directory_assignment_mode",
            field=models.CharField(choices=[("auto", "Auto"), ("manual", "Manual")], default="auto", max_length=10),
        ),
        migrations.AddField(
            model_name="material",
            name="source_folder_path",
            field=models.CharField(blank=True, default="", max_length=1024),
        ),
        migrations.AddField(
            model_name="material",
            name="source_identity",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="material",
            name="source_relative_path",
            field=models.CharField(blank=True, default="", max_length=1024),
        ),
        migrations.AddField(
            model_name="wikiknowledgebase",
            name="directory_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="pagerelation",
            name="from_page",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="relations_out", to="opspilot.knowledgepage"),
        ),
        migrations.AlterField(
            model_name="pagerelation",
            name="to_page",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="relations_in", to="opspilot.knowledgepage"),
        ),
        migrations.AddField(
            model_name="wikistructurerevision",
            name="knowledge_base",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="structure_revisions", to="opspilot.wikiknowledgebase"),
        ),
        migrations.AddField(
            model_name="wikiimportpreflight",
            name="base_generation",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="import_preflights", to="opspilot.wikigeneration"
            ),
        ),
        migrations.AddField(
            model_name="wikiimportpreflight",
            name="classification_root",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="import_preflights", to="opspilot.wikidirectory"
            ),
        ),
        migrations.AddField(
            model_name="wikiimportpreflight",
            name="knowledge_base",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="import_preflights", to="opspilot.wikiknowledgebase"),
        ),
        migrations.AddField(
            model_name="wikiimportpreflight",
            name="structure_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="import_preflights",
                to="opspilot.wikistructurerevision",
            ),
        ),
        migrations.AddField(
            model_name="wikigenerationpage",
            name="directory",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="generation_memberships", to="opspilot.wikidirectory"),
        ),
        migrations.AddField(
            model_name="wikigenerationpage",
            name="generation",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="page_members", to="opspilot.wikigeneration"),
        ),
        migrations.AddField(
            model_name="wikigenerationpage",
            name="page",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="generation_memberships", to="opspilot.knowledgepage"),
        ),
        migrations.AddField(
            model_name="wikigenerationpage",
            name="page_version",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="generation_memberships", to="opspilot.pageversion"),
        ),
        migrations.AddField(
            model_name="wikigenerationoverview",
            name="directory",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="generation_overviews", to="opspilot.wikidirectory"
            ),
        ),
        migrations.AddField(
            model_name="wikigenerationoverview",
            name="generation",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="overviews", to="opspilot.wikigeneration"),
        ),
        migrations.AddField(
            model_name="wikigenerationindexentry",
            name="directory",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="generation_index_entries", to="opspilot.wikidirectory"
            ),
        ),
        migrations.AddField(
            model_name="wikigenerationindexentry",
            name="generation",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="index_entries", to="opspilot.wikigeneration"),
        ),
        migrations.AddField(
            model_name="wikigenerationindexentry",
            name="page",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="generation_index_entries", to="opspilot.knowledgepage"
            ),
        ),
        migrations.AddField(
            model_name="wikigenerationindexentry",
            name="page_version",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="generation_index_entries", to="opspilot.pageversion"),
        ),
        migrations.AddField(
            model_name="wikigeneration",
            name="base_generation",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="derived_generations", to="opspilot.wikigeneration"
            ),
        ),
        migrations.AddField(
            model_name="wikigeneration",
            name="build_record",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="generations", to="opspilot.buildrecord"
            ),
        ),
        migrations.AddField(
            model_name="wikigeneration",
            name="knowledge_base",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="generations", to="opspilot.wikiknowledgebase"),
        ),
        migrations.AddField(
            model_name="wikigeneration",
            name="rollback_of",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="rollback_generations", to="opspilot.wikigeneration"
            ),
        ),
        migrations.AddField(
            model_name="wikigeneration",
            name="structure_revision",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="generations", to="opspilot.wikistructurerevision"),
        ),
        migrations.AddField(
            model_name="wikidirectory",
            name="knowledge_base",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="directories", to="opspilot.wikiknowledgebase"),
        ),
        migrations.AddField(
            model_name="wikidirectory",
            name="merged_into",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="merged_directories", to="opspilot.wikidirectory"
            ),
        ),
        migrations.AddField(
            model_name="wikidirectory",
            name="parent",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="opspilot.wikidirectory"
            ),
        ),
        migrations.AddField(
            model_name="pagedirectorychange",
            name="from_directory",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="directory_changes_from", to="opspilot.wikidirectory"
            ),
        ),
        migrations.AddField(
            model_name="pagedirectorychange",
            name="generation",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="directory_changes", to="opspilot.wikigeneration"),
        ),
        migrations.AddField(
            model_name="pagedirectorychange",
            name="page",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="directory_changes", to="opspilot.knowledgepage"),
        ),
        migrations.AddField(
            model_name="pagedirectorychange",
            name="structure_revision",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="page_directory_changes", to="opspilot.wikistructurerevision"
            ),
        ),
        migrations.AddField(
            model_name="pagedirectorychange",
            name="to_directory",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="directory_changes_to", to="opspilot.wikidirectory"),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="base_generation",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="based_build_records", to="opspilot.wikigeneration"
            ),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="generation",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="primary_build_records", to="opspilot.wikigeneration"
            ),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="rollback_of_generation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rollback_build_records",
                to="opspilot.wikigeneration",
            ),
        ),
        migrations.AddField(
            model_name="buildrecord",
            name="structure_revision",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="build_records", to="opspilot.wikistructurerevision"
            ),
        ),
        migrations.AddField(
            model_name="knowledgepage",
            name="directory",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pages", to="opspilot.wikidirectory"
            ),
        ),
        migrations.AddField(
            model_name="material",
            name="classification_root",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="source_materials", to="opspilot.wikidirectory"
            ),
        ),
        migrations.AddField(
            model_name="pagerelation",
            name="generation",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="relations", to="opspilot.wikigeneration"
            ),
        ),
        migrations.AddConstraint(
            model_name="pagerelation",
            constraint=models.UniqueConstraint(fields=("generation", "from_page", "to_page", "relation_type"), name="uniq_wiki_rel_generation"),
        ),
        migrations.AddField(
            model_name="pageversion",
            name="created_in_generation",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_page_versions", to="opspilot.wikigeneration"
            ),
        ),
        migrations.AddField(
            model_name="wikiknowledgebase",
            name="active_generation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="active_for_knowledge_bases",
                to="opspilot.wikigeneration",
            ),
        ),
        migrations.AddField(
            model_name="wikiknowledgebase",
            name="active_structure_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="active_for_knowledge_bases",
                to="opspilot.wikistructurerevision",
            ),
        ),
        migrations.AddConstraint(
            model_name="wikistructurerevision",
            constraint=models.UniqueConstraint(fields=("knowledge_base", "revision_no"), name="uniq_wiki_structure_revision_no"),
        ),
        migrations.AddIndex(
            model_name="wikiimportpreflight",
            index=models.Index(fields=["knowledge_base", "status", "expires_at"], name="wiki_import_preflight_idx"),
        ),
        migrations.AddIndex(
            model_name="wikigenerationpage",
            index=models.Index(fields=["generation", "directory", "page_status"], name="wiki_gen_page_scope_idx"),
        ),
        migrations.AddConstraint(
            model_name="wikigenerationpage",
            constraint=models.UniqueConstraint(fields=("generation", "page"), name="uniq_wiki_generation_page"),
        ),
        migrations.AddConstraint(
            model_name="wikigenerationpage",
            constraint=models.CheckConstraint(check=models.Q(("page_status", "active")), name="wiki_gen_page_active_only"),
        ),
        migrations.AddIndex(
            model_name="wikigenerationoverview",
            index=models.Index(fields=["generation", "directory"], name="wiki_gen_overview_scope_idx"),
        ),
        migrations.AddConstraint(
            model_name="wikigenerationoverview",
            constraint=models.UniqueConstraint(fields=("generation", "scope_key"), name="uniq_wiki_gen_overview_scope"),
        ),
        migrations.AddIndex(
            model_name="wikigenerationindexentry",
            index=models.Index(fields=["generation", "normalized_title"], name="wiki_gen_idx_title_idx"),
        ),
        migrations.AddIndex(
            model_name="wikigenerationindexentry",
            index=models.Index(fields=["generation", "directory", "page_type"], name="wiki_gen_idx_scope_idx"),
        ),
        migrations.AddConstraint(
            model_name="wikigenerationindexentry",
            constraint=models.UniqueConstraint(fields=("generation", "page"), name="uniq_wiki_gen_index_page"),
        ),
        migrations.AddIndex(
            model_name="wikigeneration",
            index=models.Index(fields=["knowledge_base", "status", "created_at"], name="wiki_gen_status_idx"),
        ),
        migrations.AddIndex(
            model_name="wikidirectory",
            index=models.Index(fields=["knowledge_base", "status", "parent", "sort_order"], name="wiki_dir_tree_idx"),
        ),
        migrations.AddConstraint(
            model_name="wikidirectory",
            constraint=models.UniqueConstraint(fields=("knowledge_base", "key"), name="uniq_wiki_directory_key"),
        ),
        migrations.AddIndex(
            model_name="pagedirectorychange",
            index=models.Index(fields=["page", "created_at"], name="wiki_page_dir_change_idx"),
        ),
    ]
