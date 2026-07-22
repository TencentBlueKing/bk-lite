# Historical Superpowers change: 2026-06-22-opspilot-wiki-p0-foundation

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-22-opspilot-wiki-p0-foundation.md

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 或 executing-plans 逐任务实现。步骤用 `- [ ]`。

**Goal:** 搭好新 Wiki 的数据模型、知识库 CRUD(团队权限)、Purpose/Schema(Markdown+模板+AI 辅助)、创建知识库流程、资料解析 loader(从 git 恢复)、MinIO 存储——即 P1 构建管道之前的全部地基。

**Architecture:** 在 `apps/opspilot` 新增 `models/wiki_mgmt.py`(page-centric 模型)+ `services/wiki/`(服务)+ 恢复 `metis/llm/loader/`;DRF viewset/serializer 提供 KB CRUD 与创建流程;Purpose/Schema 存 Markdown 文本字段,模板内置 + 复用 metis LLM 生成。检索/构建管道不在 P0。

**Tech Stack:** Django 4.2 / DRF / Celery / `django_minio_backend` / metis `llm_client_factory`;测试 pytest(venv `D:\app\venv\bkliteserver`,`-o addopts=""`)。

**工作目录:** worktree `kb-remove`(`D:\app\github\bk-lite\.claude\worktrees\kb-remove`),分支 `claude/bold-tu-40b23d`。提交只在分支,不合并 master、不 push。

**前置状态:** worktree 处于 merge(未提交);其中含一条裸删除迁移 `0059_remove_fileknowledge_knowledge_document_and_more.py`(依赖 master 的 `0058_bot_usage_team`)。P0 用"转换式迁移"思路:**保留删 RAG 旧表的操作,但同一迁移里追加新 wiki 表的创建**(旧数据不保留)。

---

## 文件结构(P0 创建/修改)

- Create: `server/apps/opspilot/models/wiki_mgmt.py` — 9 个核心模型
- Modify: `server/apps/opspilot/models/__init__.py` — 导出新模型
- Restore(git): `server/apps/opspilot/metis/llm/loader/*.py` — 10 个 loader
- Create: `server/apps/opspilot/services/wiki/__init__.py`
- Create: `server/apps/opspilot/services/wiki/purpose_schema_service.py` — 模板 + AI 辅助生成
- Create: `server/apps/opspilot/serializers/wiki_serializers.py`
- Create: `server/apps/opspilot/viewsets/wiki_kb_view.py` — KnowledgeBase CRUD + 创建流程 + 模板
- Modify: `server/apps/opspilot/viewsets/__init__.py`、`serializers/__init__.py`、`urls.py` — 注册
- Migration: `server/apps/opspilot/migrations/00XX_wiki_*.py`(由 makemigrations 生成)
- Tests: `server/apps/opspilot/tests/wiki/test_models_pure.py`、`test_wiki_kb_views.py`、`test_purpose_schema_service.py`

---

## Task 1: 恢复资料解析 loader(从 git)

**Files:** Restore: `server/apps/opspilot/metis/llm/loader/*.py`

- [ ] **Step 1: 从 git 恢复 loader 目录**

```bash
cd /d/app/github/bk-lite/.claude/worktrees/kb-remove
git checkout e7b71e00c^ -- server/apps/opspilot/metis/llm/loader/
```

- [ ] **Step 2: 验证导入(loader 不应依赖已删的 rag/chunk/embed)**

```bash
cd server && /d/app/venv/bkliteserver/Scripts/python.exe -c "import apps.opspilot.metis.llm.loader.pdf_loader, apps.opspilot.metis.llm.loader.website_loader, apps.opspilot.metis.llm.loader.text_loader"
```
Expected: 无 ImportError。若某 loader import 了已删模块(如 chunk),记录并在 Task 1b 处理。

- [ ] **Step 3: 处理 loader 的悬空依赖(若 Step 2 报错)**

grep `from apps.opspilot.metis.llm.(chunk|embed|rag|rerank)` loader 目录;P0 只需"解析为文本/图片"的能力,删除/桩掉对 chunk/embed 的引用(那是 P6 向量期才用)。

- [ ] **Step 4: 提交**

```bash
git add server/apps/opspilot/metis/llm/loader/
git commit -m "feat(wiki): 恢复资料解析 loader(P0)"
```

---

## Task 2: 核心数据模型 `wiki_mgmt.py`

**Files:** Create `server/apps/opspilot/models/wiki_mgmt.py`; Modify `models/__init__.py`
**Test:** `server/apps/opspilot/tests/wiki/test_models_pure.py`

- [ ] **Step 1: 写失败测试(模型可导入 + 关键字段/默认值)**

```python
# server/apps/opspilot/tests/wiki/test_models_pure.py
import pytest


@pytest.mark.django_db
def test_wiki_models_importable_and_defaults():
    from apps.opspilot.models import (
        WikiKnowledgeBase, Material, MaterialVersion, KnowledgePage,
        PageVersion, PageRelation, PageEvidence, BuildRecord, CheckItem,
    )
    kb = WikiKnowledgeBase.objects.create(name="kb1", team=[1], purpose_md="# P", schema_md="# S")
    assert kb.status == "active"
    m = Material.objects.create(knowledge_base=kb, name="m1", material_type="text", status="pending")
    assert m.material_type == "text" and m.status == "pending"
    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title="t", contribution="ai")
    pv = PageVersion.objects.create(page=page, no=1, body="b", change_type="ai_create", is_current=True)
    assert pv.is_current is True
```

- [ ] **Step 2: 运行确认失败**

```bash
cd server && /d/app/venv/bkliteserver/Scripts/python.exe -m pytest apps/opspilot/tests/wiki/test_models_pure.py -o addopts="" -p no:cacheprovider -q
```
Expected: FAIL(ImportError: cannot import name 'WikiKnowledgeBase')

- [ ] **Step 3: 实现模型**

新建 `server/apps/opspilot/models/wiki_mgmt.py`(复用 `MaintainerInfo`/`TimeInfo` 基类,参考 `model_provider_mgmt.py` 的引入方式):

```python
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_minio_backend.models import MinioBackend, iso_date_prefix

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class WikiKnowledgeBase(MaintainerInfo, TimeInfo):
    """新 Wiki 知识库本体。独立资产,多智能体复用。"""
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
    status = models.CharField(max_length=20, default="active")  # active/archived

    class Meta:
        db_table = "opspilot_wiki_knowledge_base"


class Material(MaintainerInfo, TimeInfo):
    """资料:文件/网页/文本。原始证据 + AI 摘要。"""
    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="materials")
    name = models.CharField(max_length=255, db_index=True)
    material_type = models.CharField(max_length=20)  # file/web/text
    file = models.FileField(storage=MinioBackend(bucket_name="munchkin-private"), upload_to=iso_date_prefix, null=True, blank=True)
    url = models.URLField(blank=True, default="")
    text_content = models.TextField(blank=True, default="")
    content_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ai_summary = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, default="pending")  # pending/building/done/partial/failed/updated/invalid
    current_version = models.ForeignKey("MaterialVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_material"


class MaterialVersion(TimeInfo):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="versions")
    content_locator = models.TextField(blank=True, default="")  # MinIO path / url snapshot ref
    content_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_material_version"


class KnowledgePage(MaintainerInfo, TimeInfo):
    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="pages")
    page_type = models.CharField(max_length=50)  # schema-defined
    title = models.CharField(max_length=255, db_index=True)
    tags = models.JSONField(default=list)
    current_version = models.ForeignKey("PageVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    contribution = models.CharField(max_length=20, default="ai")  # ai/human/mixed
    update_method = models.CharField(max_length=30, blank=True, default="")
    status = models.CharField(max_length=20, default="active")  # active/archived/source_invalid

    class Meta:
        db_table = "opspilot_wiki_page"


class PageVersion(TimeInfo):
    page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="page_versions")
    no = models.IntegerField(default=1)
    body = models.TextField(default="")
    meta_snapshot = models.JSONField(default=dict)
    change_type = models.CharField(max_length=30)  # human_edit/ai_create/ai_merge/material_update/rebuild/restore/candidate
    build_record = models.ForeignKey("BuildRecord", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_current = models.BooleanField(default=False)
    created_by = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        db_table = "opspilot_wiki_page_version"


class PageRelation(TimeInfo):
    from_page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="relations_out")
    to_page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="relations_in")
    relation_type = models.CharField(max_length=30)  # reference/shared_source/ai_identified
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


class BuildRecord(MaintainerInfo, TimeInfo):
    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="build_records")
    trigger = models.CharField(max_length=30, default="material")  # material/rebuild/material_update/material_delete
    operator = models.CharField(max_length=100, blank=True, default="")
    inputs = models.JSONField(default=dict)
    stage = models.CharField(max_length=30, default="queued")
    progress = models.FloatField(default=0)
    counts = models.JSONField(default=dict)  # {new, updated, unchanged, pending_review}
    affected_pages = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    status = models.CharField(max_length=20, default="running")  # running/success/partial/failed

    class Meta:
        db_table = "opspilot_wiki_build_record"


class CheckItem(MaintainerInfo, TimeInfo):
    knowledge_base = models.ForeignKey(WikiKnowledgeBase, on_delete=models.CASCADE, related_name="check_items")
    check_type = models.CharField(max_length=40)  # conflict/duplicate/stale/missing/orphan/broken_relation/no_source/low_confidence/cannot_merge/all_sources_invalid/schema_mismatch
    status = models.CharField(max_length=20, default="open")  # open/resolved/dismissed
    related = models.JSONField(default=dict)  # {pages:[], materials:[]}
    candidate_version = models.ForeignKey(PageVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    suggested_actions = models.JSONField(default=list)

    class Meta:
        db_table = "opspilot_wiki_check_item"
```

> 实现前先确认 `MaintainerInfo`/`TimeInfo` 的真实导入路径(grep `class MaintainerInfo`),按实际路径修正 import。

- [ ] **Step 4: 导出模型**

在 `models/__init__.py` 追加:
```python
from apps.opspilot.models.wiki_mgmt import (  # noqa
    WikiKnowledgeBase, Material, MaterialVersion, KnowledgePage,
    PageVersion, PageRelation, PageEvidence, BuildRecord, CheckItem,
)
```
并加入 `__all__`(若该文件维护 `__all__`)。

- [ ] **Step 5: 生成迁移(转换式:同一迁移里删旧 RAG 表 + 建新 wiki 表)**

```bash
cd server && /d/app/venv/bkliteserver/Scripts/python.exe manage.py makemigrations opspilot
```
Expected: 生成含 9 个 `CreateModel` 的迁移(旧表的删除仍由现有 `0059` 承担;新表迁移依赖 `0059`)。检查依赖链线性。

- [ ] **Step 6: 运行测试通过**

```bash
/d/app/venv/bkliteserver/Scripts/python.exe -m pytest apps/opspilot/tests/wiki/test_models_pure.py -o addopts="" --create-db -p no:cacheprovider -q
```
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add server/apps/opspilot/models/ server/apps/opspilot/tests/wiki/
git commit -m "feat(wiki): 核心数据模型 wiki_mgmt(P0)"
```

---

## Task 3: Purpose/Schema 模板 + AI 辅助生成服务

**Files:** Create `server/apps/opspilot/services/wiki/__init__.py`、`purpose_schema_service.py`
**Test:** `server/apps/opspilot/tests/wiki/test_purpose_schema_service.py`

- [ ] **Step 1: 写失败测试(模板返回 + AI 生成 mock)**

```python
import pytest
from unittest.mock import patch


def test_templates_listed():
    from apps.opspilot.services.wiki.purpose_schema_service import list_templates
    keys = {t["key"] for t in list_templates()}
    assert {"ops_qa", "fault_diagnosis", "operation_guide", "product_support", "general"} <= keys


def test_generate_purpose_schema_uses_template_and_llm():
    from apps.opspilot.services.wiki.purpose_schema_service import generate_purpose_schema
    with patch("apps.opspilot.services.wiki.purpose_schema_service._llm_generate", return_value=("# Purpose\nX", "# Schema\nY")):
        purpose, schema = generate_purpose_schema(template_key="ops_qa", description="运维问答库", llm_model_id=None)
    assert purpose.startswith("# Purpose") and schema.startswith("# Schema")
```

- [ ] **Step 2: 运行确认失败**

```bash
cd server && /d/app/venv/bkliteserver/Scripts/python.exe -m pytest apps/opspilot/tests/wiki/test_purpose_schema_service.py -o addopts="" -p no:cacheprovider -q
```
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 实现服务**

`services/wiki/purpose_schema_service.py`:5 个模板(ops_qa/fault_diagnosis/operation_guide/product_support/general),每个含默认 `purpose_md`/`schema_md` 骨架;`generate_purpose_schema(template_key, description, llm_model_id)` 用模板 + 描述构造 prompt,`_llm_generate` 调 `metis.llm.common.llm_client_factory`(无 llm_model_id 时直接返回模板骨架)。`list_templates()` 返回模板元数据。

- [ ] **Step 4: 运行测试通过**

```bash
/d/app/venv/bkliteserver/Scripts/python.exe -m pytest apps/opspilot/tests/wiki/test_purpose_schema_service.py -o addopts="" -p no:cacheprovider -q
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/apps/opspilot/services/wiki/ server/apps/opspilot/tests/wiki/test_purpose_schema_service.py
git commit -m "feat(wiki): Purpose/Schema 模板与 AI 辅助生成服务(P0)"
```

---

## Task 4: KnowledgeBase CRUD + 创建流程 + 模板接口(DRF)

**Files:** Create `serializers/wiki_serializers.py`、`viewsets/wiki_kb_view.py`;Modify `viewsets/__init__.py`、`serializers/__init__.py`、`urls.py`
**Test:** `server/apps/opspilot/tests/wiki/test_wiki_kb_views.py`

- [ ] **Step 1: 写失败测试(创建/列表/团队过滤/模板/生成)**

```python
import pytest


@pytest.mark.django_db
class TestWikiKBViews:
    def test_create_and_list(self, api_client):
        resp = api_client.post("/api/v1/opspilot/wiki_mgmt/knowledge_base/",
                               {"name": "kb1", "team": [1], "purpose_md": "# P", "schema_md": "# S"}, format="json")
        assert resp.status_code in (200, 201)
        lst = api_client.get("/api/v1/opspilot/wiki_mgmt/knowledge_base/")
        assert any(x["name"] == "kb1" for x in (lst.json().get("data", lst.json())))

    def test_templates_endpoint(self, api_client):
        resp = api_client.get("/api/v1/opspilot/wiki_mgmt/knowledge_base/templates/")
        assert resp.status_code == 200
```
(用全局 `api_client` fixture;团队权限沿用现有 `AuthViewSet`/`TeamPermissionMixin` 模式。)

- [ ] **Step 2: 运行确认失败**

```bash
cd server && /d/app/venv/bkliteserver/Scripts/python.exe -m pytest apps/opspilot/tests/wiki/test_wiki_kb_views.py -o addopts="" --create-db -p no:cacheprovider -q
```
Expected: FAIL(404 / NoReverseMatch)

- [ ] **Step 3: 实现 serializer + viewset + 路由**

- `WikiKnowledgeBaseSerializer`(参考 `llm_serializer.py` 的 `AuthSerializer`/`TeamSerializer` 模式)。
- `WikiKnowledgeBaseViewSet(AuthViewSet)`:标准 CRUD + `@action templates`(GET,调 `list_templates`)+ `@action generate_purpose_schema`(POST,调 `generate_purpose_schema`)。团队过滤复用 `query_by_groups`/权限装饰器(参考 `bot_view.py`/`llm_view.py`)。
- `urls.py` 注册 `router.register(r"wiki_mgmt/knowledge_base", WikiKnowledgeBaseViewSet)`;`viewsets/__init__.py`、`serializers/__init__.py` 导出。

- [ ] **Step 4: 运行测试通过**

```bash
/d/app/venv/bkliteserver/Scripts/python.exe -m pytest apps/opspilot/tests/wiki/test_wiki_kb_views.py -o addopts="" --create-db -p no:cacheprovider -q
```
Expected: PASS

- [ ] **Step 5: system check + 迁移检查**

```bash
/d/app/venv/bkliteserver/Scripts/python.exe manage.py check
/d/app/venv/bkliteserver/Scripts/python.exe manage.py makemigrations --check --dry-run
```
Expected: check 无问题;无未生成迁移。

- [ ] **Step 6: 提交**

```bash
git add server/apps/opspilot/serializers/ server/apps/opspilot/viewsets/ server/apps/opspilot/urls.py server/apps/opspilot/tests/wiki/test_wiki_kb_views.py
git commit -m "feat(wiki): 知识库 CRUD + 创建流程 + 模板接口(P0)"
```

---

## Task 5: P0 收尾验证

- [ ] **Step 1: 跑全部 wiki 测试**

```bash
cd server && /d/app/venv/bkliteserver/Scripts/python.exe -m pytest apps/opspilot/tests/wiki/ -o addopts="" --create-db -p no:cacheprovider -q
```
Expected: 全 PASS。

- [ ] **Step 2: 后端整体不回归(抽样)**

```bash
/d/app/venv/bkliteserver/Scripts/python.exe manage.py check
```
Expected: 无问题。

- [ ] **Step 3: flake8/isort/black(后端代码质量)**

```bash
cd server && /d/app/venv/bkliteserver/Scripts/python.exe -m flake8 apps/opspilot/models/wiki_mgmt.py apps/opspilot/services/wiki apps/opspilot/viewsets/wiki_kb_view.py
```
Expected: 无错误(按需 isort/black 格式化)。

---

## 自检(spec 覆盖)
- 数据模型(架构 §3)→ Task 2 ✅
- Purpose/Schema MD + 模板 + AI 辅助(§5/§4.6)→ Task 3、Task 4 ✅
- KB CRUD + 团队权限 + 创建流程(§4.6/§5/§14)→ Task 4 ✅
- 资料解析 loader 复用(§7)→ Task 1 ✅
- MinIO 存储(§3)→ Task 2(Material.file)✅
- 转换式迁移(§7)→ Task 2 Step 5 ✅
- 构建管道/检索/问答/前端 → P1+(不在 P0)
