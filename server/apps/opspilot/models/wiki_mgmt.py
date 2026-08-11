from django.db import models
from django.utils.translation import gettext_lazy as _
from django_minio_backend.models import MinioBackend, iso_date_prefix

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class WikiKnowledgeBase(MaintainerInfo, TimeInfo):
    """新 Wiki 知识库本体:由 AI 持续构建/维护、供多个智能体复用的结构化知识资产。"""

    name = models.CharField(max_length=100, db_index=True)
    introduction = models.TextField(blank=True, default="")
    team = models.JSONField(default=list)
    purpose_md = models.TextField(default="", verbose_name=_("Purpose Markdown"))
    schema_md = models.TextField(default="", verbose_name=_("Schema Markdown"))
    llm_model = models.ForeignKey("LLMModel", null=True, blank=True, on_delete=models.SET_NULL)
    embed_provider = models.ForeignKey("EmbedProvider", null=True, blank=True, on_delete=models.SET_NULL)
    vision_model = models.ForeignKey("LLMModel", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    generation_language = models.CharField(max_length=20, default="zh")
    generation_rules = models.JSONField(default=dict)
    web_sync_policy = models.JSONField(default=dict)
    risk_rules = models.JSONField(default=dict)
    template_key = models.CharField(max_length=50, default="general")
    status = models.CharField(max_length=20, default="active")  # active / archived
    active_structure_revision = models.ForeignKey(
        "WikiStructureRevision",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="active_for_knowledge_bases",
    )
    active_generation = models.ForeignKey(
        "WikiGeneration",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="active_for_knowledge_bases",
    )
    directory_enabled = models.BooleanField(default=False)
    directory_migration_state = models.CharField(
        max_length=20,
        default="legacy",
        db_index=True,
        help_text="legacy / backfilling / ready / enabled",
    )

    class Meta:
        db_table = "opspilot_wiki_knowledge_base"

    def __str__(self):
        return self.name


class WikiStructureRevision(MaintainerInfo, TimeInfo):
    """知识库不可变目录结构快照。"""

    knowledge_base = models.ForeignKey(
        WikiKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="structure_revisions",
    )
    revision_no = models.PositiveIntegerField()
    structure_snapshot = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64, db_index=True)

    class Meta:
        db_table = "opspilot_wiki_structure_revision"
        ordering = ["-revision_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["knowledge_base", "revision_no"],
                name="uniq_wiki_structure_revision_no",
            )
        ]


class WikiDirectory(MaintainerInfo, TimeInfo):
    """当前活动结构的规范化目录投影。"""

    ORIGIN_CHOICES = (
        ("system", "System"),
        ("schema", "Schema"),
        ("manual", "Manual"),
    )
    STATUS_CHOICES = (
        ("active", "Active"),
        ("retired", "Retired"),
        ("merged", "Merged"),
        ("archived", "Archived"),
    )

    knowledge_base = models.ForeignKey(
        WikiKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="directories",
    )
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    sort_order = models.IntegerField(default=0)
    origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default="manual")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    accepts_pages = models.BooleanField(default=True)
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="merged_directories",
    )

    class Meta:
        db_table = "opspilot_wiki_directory"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["knowledge_base", "key"],
                name="uniq_wiki_directory_key",
            )
        ]
        indexes = [
            models.Index(
                fields=["knowledge_base", "status", "parent", "sort_order"],
                name="wiki_dir_tree_idx",
            )
        ]

    @property
    def is_system(self):
        return self.origin == "system"

    def __str__(self):
        return self.name


class Material(MaintainerInfo, TimeInfo):
    """资料:文件/网页/文本。原始事实证据,并生成 AI 摘要。"""

    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="materials")
    name = models.CharField(max_length=255, db_index=True)
    material_type = models.CharField(max_length=20)  # file / web / text
    file = models.FileField(
        storage=MinioBackend(bucket_name="munchkin-private"),
        upload_to=iso_date_prefix,
        null=True,
        blank=True,
    )
    url = models.URLField(blank=True, default="")
    # 网页资料的定时刷新策略(按站点单独配置):{"enabled": bool, "interval_hours": int}
    sync_policy = models.JSONField(default=dict)
    text_content = models.TextField(blank=True, default="")
    ocr_enhance = models.BooleanField(default=False)
    source_relative_path = models.CharField(max_length=1024, blank=True, default="")
    source_identity = models.CharField(max_length=255, blank=True, default="", db_index=True)
    source_folder_path = models.CharField(max_length=1024, blank=True, default="")
    classification_root = models.ForeignKey(
        WikiDirectory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="source_materials",
    )
    content_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ai_summary = models.TextField(blank=True, default="")
    # 用户只看到未构建/排队中/构建中/构建成功/构建失败；内部保留阶段 key 供排障。
    # pending / queued / parsing / done / building / built / parse_failed /
    # build_failed / updated / invalid
    status = models.CharField(max_length=20, default="pending")
    current_version = models.ForeignKey(
        "MaterialVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_material"

    def __str__(self):
        return self.name


class MaterialVersion(TimeInfo):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="versions")
    content_locator = models.TextField(blank=True, default="")  # MinIO path / 网页快照引用
    content_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_material_version"


class WikiImageCaption(TimeInfo):
    image_hash = models.CharField(max_length=64, unique=True, db_index=True)
    caption = models.TextField(default="")
    vision_model = models.ForeignKey("LLMModel", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "opspilot_wiki_image_caption"


class KnowledgePage(MaintainerInfo, TimeInfo):
    DIRECTORY_ASSIGNMENT_MODES = (
        ("auto", "Auto"),
        ("manual", "Manual"),
    )

    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="pages")
    page_type = models.CharField(max_length=50)  # 由 schema 定义
    title = models.CharField(max_length=255, db_index=True)
    tags = models.JSONField(default=list)
    current_version = models.ForeignKey(
        "PageVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    contribution = models.CharField(max_length=20, default="ai")  # ai / human / mixed
    update_method = models.CharField(max_length=30, blank=True, default="")
    status = models.CharField(max_length=20, default="active")  # active / archived / source_invalid
    directory = models.ForeignKey(
        WikiDirectory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pages",
    )
    directory_assignment_mode = models.CharField(
        max_length=10,
        choices=DIRECTORY_ASSIGNMENT_MODES,
        default="auto",
    )

    class Meta:
        db_table = "opspilot_wiki_page"

    def __str__(self):
        return self.title


class PageVersion(TimeInfo):
    page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="page_versions")
    no = models.IntegerField(default=1)
    body = models.TextField(default="")
    # 语义索引:构建/编辑时生成的正文嵌入向量(JSON 存储,无需 pgvector;规模化可换 pgvector 列)
    embedding = models.JSONField(default=list, blank=True)
    meta_snapshot = models.JSONField(default=dict)
    # human_edit / ai_create / ai_merge / material_update / rebuild / restore / candidate
    change_type = models.CharField(max_length=30)
    build_record = models.ForeignKey(
        "BuildRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_in_generation = models.ForeignKey(
        "WikiGeneration",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_page_versions",
    )
    is_current = models.BooleanField(default=False)
    created_by = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_page_version"


class WikiGeneration(MaintainerInfo, TimeInfo):
    """一次不可变的知识集合发布候选或历史快照。"""

    KIND_CHOICES = (
        ("build", "Build"),
        ("governance", "Governance"),
        ("rollback", "Rollback"),
    )
    STATUS_CHOICES = (
        ("preparing", "Preparing"),
        ("ready", "Ready"),
        ("active", "Active"),
        ("superseded", "Superseded"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    )

    knowledge_base = models.ForeignKey(
        WikiKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="generations",
    )
    build_record = models.ForeignKey(
        "BuildRecord",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="generations",
    )
    structure_revision = models.ForeignKey(
        WikiStructureRevision,
        on_delete=models.PROTECT,
        related_name="generations",
    )
    base_generation = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="derived_generations",
    )
    rollback_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rollback_generations",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    structure_fingerprint = models.CharField(max_length=64, db_index=True)
    pipeline_version = models.CharField(max_length=64)
    source_fingerprints = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="preparing", db_index=True)

    class Meta:
        db_table = "opspilot_wiki_generation"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["knowledge_base", "status", "created_at"],
                name="wiki_gen_status_idx",
            )
        ]


class WikiGenerationPage(TimeInfo):
    """generation 的完整页面成员及其冻结显示快照。"""

    generation = models.ForeignKey(
        WikiGeneration,
        on_delete=models.PROTECT,
        related_name="page_members",
    )
    page = models.ForeignKey(
        KnowledgePage,
        on_delete=models.PROTECT,
        related_name="generation_memberships",
    )
    page_version = models.ForeignKey(
        PageVersion,
        on_delete=models.PROTECT,
        related_name="generation_memberships",
    )
    directory = models.ForeignKey(
        WikiDirectory,
        on_delete=models.PROTECT,
        related_name="generation_memberships",
    )
    directory_key_snapshot = models.CharField(max_length=64)
    directory_breadcrumb_snapshot = models.JSONField(default=list)
    assignment_mode = models.CharField(
        max_length=10,
        choices=KnowledgePage.DIRECTORY_ASSIGNMENT_MODES,
    )
    page_status = models.CharField(max_length=20)
    page_display_snapshot = models.JSONField(default=dict)

    class Meta:
        db_table = "opspilot_wiki_generation_page"
        constraints = [
            models.UniqueConstraint(
                fields=["generation", "page"],
                name="uniq_wiki_generation_page",
            ),
            models.CheckConstraint(
                check=models.Q(page_status="active"),
                name="wiki_gen_page_active_only",
            ),
        ]
        indexes = [
            models.Index(
                fields=["generation", "directory", "page_status"],
                name="wiki_gen_page_scope_idx",
            )
        ]


class WikiGenerationIndexEntry(TimeInfo):
    """Generation-owned compact retrieval entry for one active page version."""

    generation = models.ForeignKey(
        WikiGeneration,
        on_delete=models.PROTECT,
        related_name="index_entries",
    )
    page = models.ForeignKey(
        KnowledgePage,
        on_delete=models.PROTECT,
        related_name="generation_index_entries",
    )
    page_version = models.ForeignKey(
        PageVersion,
        on_delete=models.PROTECT,
        related_name="generation_index_entries",
    )
    directory = models.ForeignKey(
        WikiDirectory,
        on_delete=models.PROTECT,
        related_name="generation_index_entries",
    )
    title = models.CharField(max_length=255)
    normalized_title = models.CharField(max_length=255)
    aliases = models.JSONField(default=list)
    page_type = models.CharField(max_length=50, default="concept")
    tags = models.JSONField(default=list)
    directory_key = models.CharField(max_length=64)
    directory_breadcrumb = models.JSONField(default=list)
    headings = models.JSONField(default=list)
    keywords = models.JSONField(default=list)
    entities = models.JSONField(default=list)
    summary = models.TextField(blank=True, default="")
    search_text = models.TextField(blank=True, default="")
    content_fingerprint = models.CharField(max_length=64, db_index=True)

    class Meta:
        db_table = "opspilot_wiki_generation_index_entry"
        constraints = [
            models.UniqueConstraint(
                fields=["generation", "page"],
                name="uniq_wiki_gen_index_page",
            )
        ]
        indexes = [
            models.Index(
                fields=["generation", "normalized_title"],
                name="wiki_gen_idx_title_idx",
            ),
            models.Index(
                fields=["generation", "directory", "page_type"],
                name="wiki_gen_idx_scope_idx",
            ),
        ]


class WikiGenerationOverview(TimeInfo):
    """Deterministic navigation overview plus optional semantic enhancement."""

    SEMANTIC_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("ready", "Ready"),
        ("degraded", "Degraded"),
        ("skipped", "Skipped"),
    )

    generation = models.ForeignKey(
        WikiGeneration,
        on_delete=models.PROTECT,
        related_name="overviews",
    )
    directory = models.ForeignKey(
        WikiDirectory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="generation_overviews",
    )
    scope_key = models.CharField(max_length=64)
    deterministic_text = models.TextField(default="")
    semantic_text = models.TextField(blank=True, default="")
    semantic_status = models.CharField(
        max_length=20,
        choices=SEMANTIC_STATUS_CHOICES,
        default="pending",
    )
    referenced_page_ids = models.JSONField(default=list)
    content_fingerprint = models.CharField(max_length=64, db_index=True)

    class Meta:
        db_table = "opspilot_wiki_generation_overview"
        constraints = [
            models.UniqueConstraint(
                fields=["generation", "scope_key"],
                name="uniq_wiki_gen_overview_scope",
            )
        ]
        indexes = [
            models.Index(
                fields=["generation", "directory"],
                name="wiki_gen_overview_scope_idx",
            )
        ]


class PageDirectoryChange(MaintainerInfo, TimeInfo):
    """页面目录与归类模式变更的不可变审计记录。"""

    page = models.ForeignKey(
        KnowledgePage,
        on_delete=models.PROTECT,
        related_name="directory_changes",
    )
    generation = models.ForeignKey(
        WikiGeneration,
        on_delete=models.PROTECT,
        related_name="directory_changes",
    )
    structure_revision = models.ForeignKey(
        WikiStructureRevision,
        on_delete=models.PROTECT,
        related_name="page_directory_changes",
    )
    from_directory = models.ForeignKey(
        WikiDirectory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="directory_changes_from",
    )
    to_directory = models.ForeignKey(
        WikiDirectory,
        on_delete=models.PROTECT,
        related_name="directory_changes_to",
    )
    from_assignment_mode = models.CharField(
        max_length=10,
        choices=KnowledgePage.DIRECTORY_ASSIGNMENT_MODES,
        blank=True,
        default="",
    )
    to_assignment_mode = models.CharField(
        max_length=10,
        choices=KnowledgePage.DIRECTORY_ASSIGNMENT_MODES,
    )
    source = models.CharField(max_length=30, db_index=True)
    operator = models.CharField(max_length=100, blank=True, default="")
    reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_page_directory_change"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["page", "created_at"],
                name="wiki_page_dir_change_idx",
            )
        ]


class PageRelation(TimeInfo):
    from_page = models.ForeignKey(KnowledgePage, on_delete=models.PROTECT, related_name="relations_out")
    to_page = models.ForeignKey(KnowledgePage, on_delete=models.PROTECT, related_name="relations_in")
    relation_type = models.CharField(max_length=30)  # reference / shared_source / ai_identified
    weight = models.FloatField(default=1.0)
    via_material = models.ForeignKey(Material, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    generation = models.ForeignKey(
        WikiGeneration,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="relations",
    )

    class Meta:
        db_table = "opspilot_wiki_page_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["generation", "from_page", "to_page", "relation_type"],
                name="uniq_wiki_rel_generation",
            )
        ]


class PageEvidence(TimeInfo):
    page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="evidences")
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="evidences")
    material_version = models.ForeignKey(
        MaterialVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    locator = models.TextField(blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_page_evidence"


class PageChunk(TimeInfo):
    """页面分块:按标题/段落切分当前版本正文,块级嵌入,支持细粒度语义检索(P6)。

    embedding 用 JSONField 存向量(无需 pgvector);规模化可换 pgvector 列。
    """

    page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="chunks")
    version = models.ForeignKey(PageVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    idx = models.IntegerField(default=0)
    text = models.TextField(default="")
    heading_path = models.CharField(max_length=512, blank=True, default="")
    embedding = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "opspilot_wiki_page_chunk"
        ordering = ["page_id", "idx"]


class BuildRecord(MaintainerInfo, TimeInfo):
    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="build_records")
    trigger = models.CharField(max_length=30, default="material")  # material / rebuild / material_update / material_delete
    operator = models.CharField(max_length=100, blank=True, default="")
    generation = models.ForeignKey(
        "WikiGeneration",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="primary_build_records",
    )
    base_generation = models.ForeignKey(
        "WikiGeneration",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="based_build_records",
    )
    rollback_of_generation = models.ForeignKey(
        "WikiGeneration",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rollback_build_records",
    )
    structure_revision = models.ForeignKey(
        "WikiStructureRevision",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="build_records",
    )
    structure_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    pipeline_version = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    source_fingerprints = models.JSONField(default=list)
    page_actions = models.JSONField(default=list)
    directory_trace = models.JSONField(default=list)
    activation = models.JSONField(default=dict)
    inputs = models.JSONField(default=dict)
    stage = models.CharField(max_length=30, default="queued")
    progress = models.FloatField(default=0)
    counts = models.JSONField(default=dict)  # {new, updated, unchanged, pending_review}
    affected_pages = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    maintenance = models.JSONField(default=dict)
    budget_trace = models.JSONField(default=dict)
    checkpoint = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="running")  # running / success / partial / failed

    class Meta:
        db_table = "opspilot_wiki_build_record"


class WikiImportPreflight(MaintainerInfo, TimeInfo):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("consumed", "Consumed"),
        ("expired", "Expired"),
    )

    knowledge_base = models.ForeignKey(
        WikiKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="import_preflights",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    actor = models.CharField(max_length=150)
    archive_sha256 = models.CharField(max_length=64, db_index=True)
    filename = models.CharField(max_length=255, blank=True, default="")
    archive_kind = models.CharField(max_length=20)
    base_generation = models.ForeignKey(
        WikiGeneration,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="import_preflights",
    )
    structure_revision = models.ForeignKey(
        WikiStructureRevision,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="import_preflights",
    )
    structure_version = models.PositiveIntegerField(null=True, blank=True)
    classification_root = models.ForeignKey(
        WikiDirectory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="import_preflights",
    )
    options = models.JSONField(default=dict)
    preview = models.JSONField(default=dict)
    preview_fingerprint = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", db_index=True)

    class Meta:
        db_table = "opspilot_wiki_import_preflight"
        indexes = [
            models.Index(
                fields=["knowledge_base", "status", "expires_at"],
                name="wiki_import_preflight_idx",
            )
        ]


class CheckItem(MaintainerInfo, TimeInfo):
    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="check_items")
    # conflict / duplicate / stale / missing / orphan / broken_relation / no_source /
    # low_confidence / cannot_merge / all_sources_invalid / schema_mismatch
    check_type = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="open")  # open / resolved / dismissed / auto_resolved
    related = models.JSONField(default=dict)  # {pages: [], materials: []}
    candidate_version = models.ForeignKey(PageVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    suggested_actions = models.JSONField(default=list)
    # 责任人/到期/动作类型:扩展检查项为可操作任务队列(图谱洞察、健康扫描、资料更新共用)
    assignee = models.CharField(max_length=64, blank=True, default="")
    due_at = models.DateTimeField(null=True, blank=True)
    action_type = models.CharField(max_length=40, blank=True, default="")
    # phase 1: 决策型 CheckItem 持久化稳定签名 + 冻结的决策上下文
    # 决策中心 API 用 decision_key 命中 WikiDecisionRule,context 供审计/失败提示
    decision_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    decision_context = models.JSONField(default=dict)

    class Meta:
        db_table = "opspilot_wiki_check_item"
        constraints = [
            models.CheckConstraint(
                check=(
                    ~models.Q(status="open")
                    | models.Q(
                        check_type__in=(
                            "cannot_merge",
                            "material_update",
                            "duplicate",
                            "conflict",
                        )
                    )
                ),
                name="wiki_check_open_decision_only",
            )
        ]


class WikiDecisionRule(MaintainerInfo, TimeInfo):
    """知识结果决策规则(phase 1):跨构建/重建持久化的业务结果,签名相同时自动回放。

    设计要点：
    - 同一 KB + decision_type + decision_key 在 active 状态下唯一(避免重复创建规则)
    - 主签名 = SHA-256(policy_version + kb_id + decision_type + subject_key +
      schema_fingerprint + sorted_unique(material_id, content_hash))
    - match_snapshot / result_snapshot 都是 JSON 字段(仅审计,不入查询)
    - status active|revoked:revoked 不回滚当前知识,下次同签名重新建决策
    - 物理删除/身份变化时由 phase 2 撤销服务改 status
    - decision_key = SHA-256 hex = 64 字符
    """

    DECISION_TYPE_KNOWLEDGE_CONFLICT = "knowledge_conflict"
    DECISION_TYPE_PAGE_IDENTITY = "page_identity"
    DECISION_TYPE_CHOICES = [
        (DECISION_TYPE_KNOWLEDGE_CONFLICT, "知识冲突"),
        (DECISION_TYPE_PAGE_IDENTITY, "页面身份"),
    ]

    ACTION_KEEP_CURRENT = "keep_current"
    ACTION_KEEP_ALL = "keep_all"
    ACTION_USE_NEW = "use_new"
    ACTION_EDIT_ACCEPT = "edit_accept"
    ACTION_KEEP_SEPARATE = "keep_separate"
    ACTION_MERGE = "merge"
    ACTION_CHOICES = [
        (ACTION_KEEP_CURRENT, "保留当前知识"),
        (ACTION_KEEP_ALL, "全部保留"),
        (ACTION_USE_NEW, "使用新知识"),
        (ACTION_EDIT_ACCEPT, "编辑后采用"),
        (ACTION_KEEP_SEPARATE, "保持页面独立"),
        (ACTION_MERGE, "确认页面合并"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "生效中"),
        (STATUS_REVOKED, "已撤销"),
    ]

    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="decision_rules")
    decision_type = models.CharField(max_length=40, choices=DECISION_TYPE_CHOICES, db_index=True)
    decision_key = models.CharField(max_length=64, db_index=True, help_text="SHA-256 hex,普通字段唯一约束")
    subject_key = models.CharField(max_length=200, blank=True, default="", help_text="可诊断的稳定知识标识")
    match_snapshot = models.JSONField(default=dict, help_text="参与者集合 + Schema 指纹 + 输入指纹(仅审计)")
    result_snapshot = models.JSONField(default=dict, help_text="胜出资料 + 最终正文指纹 + 目标身份(仅审计)")
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    source_check = models.ForeignKey(
        CheckItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decision_rules",
        help_text="首次创建规则的检查项(审计引用,不参与主匹配)",
    )
    result_page = models.ForeignKey(
        "KnowledgePage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_decision_rules",
        help_text="知识结果对应的页面(审计引用,知识合并时 result_page 是目标)",
    )
    result_version = models.ForeignKey(
        PageVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_decision_rules",
        help_text="最终生效的页面版本(审计引用,page_id 重建后会变,故不参与主匹配)",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    replay_count = models.IntegerField(default=0, help_text="自动回放命中次数,审计用")
    last_replayed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "opspilot_wiki_decision_rule"
        constraints = [
            models.UniqueConstraint(
                fields=["knowledge_base", "decision_type", "decision_key"],
                name="uniq_wiki_decision_rule_active",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "decision_type"]),
        ]
