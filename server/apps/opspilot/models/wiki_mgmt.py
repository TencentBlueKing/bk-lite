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
    generation_language = models.CharField(max_length=20, default="zh")
    generation_rules = models.JSONField(default=dict)
    web_sync_policy = models.JSONField(default=dict)
    risk_rules = models.JSONField(default=dict)
    template_key = models.CharField(max_length=50, default="general")
    status = models.CharField(max_length=20, default="active")  # active / archived

    class Meta:
        db_table = "opspilot_wiki_knowledge_base"

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
    text_content = models.TextField(blank=True, default="")
    content_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ai_summary = models.TextField(blank=True, default="")
    # pending / building / done / partial / failed / updated / invalid
    status = models.CharField(max_length=20, default="pending")
    current_version = models.ForeignKey("MaterialVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
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


class KnowledgePage(MaintainerInfo, TimeInfo):
    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="pages")
    page_type = models.CharField(max_length=50)  # 由 schema 定义
    title = models.CharField(max_length=255, db_index=True)
    tags = models.JSONField(default=list)
    current_version = models.ForeignKey("PageVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    contribution = models.CharField(max_length=20, default="ai")  # ai / human / mixed
    update_method = models.CharField(max_length=30, blank=True, default="")
    status = models.CharField(max_length=20, default="active")  # active / archived / source_invalid

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
    build_record = models.ForeignKey("BuildRecord", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_current = models.BooleanField(default=False)
    created_by = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_page_version"


class PageRelation(TimeInfo):
    from_page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="relations_out")
    to_page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="relations_in")
    relation_type = models.CharField(max_length=30)  # reference / shared_source / ai_identified
    weight = models.FloatField(default=1.0)
    via_material = models.ForeignKey(Material, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "opspilot_wiki_page_relation"


class PageEvidence(TimeInfo):
    page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="evidences")
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="evidences")
    material_version = models.ForeignKey(MaterialVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
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
    inputs = models.JSONField(default=dict)
    stage = models.CharField(max_length=30, default="queued")
    progress = models.FloatField(default=0)
    counts = models.JSONField(default=dict)  # {new, updated, unchanged, pending_review}
    affected_pages = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    status = models.CharField(max_length=20, default="running")  # running / success / partial / failed

    class Meta:
        db_table = "opspilot_wiki_build_record"


class CheckItem(MaintainerInfo, TimeInfo):
    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="check_items")
    # conflict / duplicate / stale / missing / orphan / broken_relation / no_source /
    # low_confidence / cannot_merge / all_sources_invalid / schema_mismatch
    check_type = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="open")  # open / resolved / dismissed
    related = models.JSONField(default=dict)  # {pages: [], materials: []}
    candidate_version = models.ForeignKey(PageVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    suggested_actions = models.JSONField(default=list)

    class Meta:
        db_table = "opspilot_wiki_check_item"
