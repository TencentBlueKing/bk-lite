"""安全更新 + 检查/审核(P2 + openspec streamline-wiki-knowledge-decisions phase 3)。

风险变更不污染当前有效版本:生成候选版本(PageVersion change_type=candidate, is_current=False)+ CheckItem。
phase 3: 决策中心 API `decide_check` 取代通用 accept/reject,
按 check_type 路由到知识冲突 3 选 1(keep_current/use_new/edit_accept)或
页面合并 2 选 1(keep_separate/merge),所有动作写入 WikiDecisionRule。
也提供系统检查扫描:孤立页面、缺来源等(MVP 子集)。
"""

import hashlib
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, PageEvidence, PageRelation, PageVersion
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.decision_service import (
    POLICY_VERSION,
    compute_decision_signature,
    compute_schema_fingerprint,
    create_rule_if_eligible,
    subject_key_for_page,
)
from apps.opspilot.services.wiki.embedding_service import clear_page_vectors
from apps.opspilot.services.wiki.graph_service import analyze_graph
from apps.opspilot.services.wiki.relation_service import LINK_RE, normalize_wikilink_key
from apps.opspilot.services.wiki.title_service import canonical_title, compact_title_key

# phase 3.1: 各 decision_type 允许的动作集合
_KNOWLEDGE_CONFLICT_ACTIONS = {"keep_current", "use_new", "edit_accept"}
_PAGE_IDENTITY_ACTIONS = {"keep_separate", "merge"}

# phase 3.4: 锁当前版本的键(供测试断言)
_LOCK_KEY = "locked_current_version_id"


def _recount_pending_review(check):
    """回算涉及该 check 的 BuildRecord.counts['pending_review'] 字段(Issue #待审批 25 飘)。

    BuildRecord.counts 是构建时的快照,后续接受/拒绝/resolve 检查时只改
    CheckItem.status,从不回写 counts,导致 BuildRecordTab 列表展示的 pending_review
    数字永远是构建时的值,与 CheckTab 实际剩余待审批不一致。

    来源:
      - check 有 candidate_version → 直接用它.build_record_id 定位 build(精确)
      - check 无 candidate_version(resolve_check 场景,如孤立页/缺来源扫描项)→
        回算 knowledge_base 下所有 build(这些检查项不绑定 build,但展示给用户
        的数字应一致;实际 KB 下的 build 数量有限,重算成本可忽略)

    save_fields 只动 counts + updated_at,避免触发 build_record 上其他字段的副作用。
    """
    if check.candidate_version_id and getattr(check.candidate_version, "build_record_id", None):
        build_ids = [check.candidate_version.build_record_id]
    else:
        build_ids = list(BuildRecord.objects.filter(knowledge_base=check.knowledge_base).values_list("id", flat=True))

    for bid in build_ids:
        build = BuildRecord.objects.filter(id=bid).first()
        if not build:
            continue
        # 仅数"通过 candidate_version 关联到此 build 且状态 open"的 CheckItem。
        # 系统扫描产生的检查(无 candidate_version)不在此计数中——它们本身没有 build 归属,
        # 但因方案 A' fallback 重算后,会反映到 KB 下所有 build 的 pending_review 里,
        # 这是当前 build.counts 数据模型能给出的最接近真实值。
        open_count = CheckItem.objects.filter(
            status="open",
            candidate_version__build_record=build,
        ).count()
        counts = dict(build.counts or {})
        if counts.get("pending_review") == open_count:
            continue
        counts["pending_review"] = open_count
        build.counts = counts
        build.save(update_fields=["counts", "updated_at"])


@transaction.atomic
def create_candidate(
    page,
    body,
    reason,
    check_type="cannot_merge",
    build_record=None,
    created_by="",
    related=None,
    suggested_actions=None,
    change_type="candidate",
    meta_snapshot=None,
):
    """为风险变更创建候选版本 + 检查事项,不改动当前有效版本。"""
    last = page.page_versions.order_by("-no").first()
    next_no = (last.no + 1) if last else 1
    candidate = PageVersion.objects.create(
        page=page,
        no=next_no,
        body=body,
        change_type=change_type,
        is_current=False,
        build_record=build_record,
        created_by=created_by or "",
        meta_snapshot=meta_snapshot or {},
    )
    check = CheckItem.objects.create(
        knowledge_base=page.knowledge_base,
        check_type=check_type,
        status="open",
        related=related or {"pages": [page.id]},
        candidate_version=candidate,
        suggested_actions=suggested_actions or ["accept", "reject", "edit_accept"],
        # phase 3.4: 锁当前版本,decide_check 时校验防止过期决策覆盖后续人工编辑
        decision_context={_LOCK_KEY: page.current_version_id} if page.current_version_id else {},
    )
    return check


@transaction.atomic
def accept_candidate(check, operator=""):
    """接受候选版本:置为当前有效版本,关闭检查。"""
    candidate = check.candidate_version
    if not candidate:
        raise ValueError("check has no candidate_version")
    page = candidate.page
    page.page_versions.filter(is_current=True).update(is_current=False)
    candidate.is_current = True
    candidate.save(update_fields=["is_current"])
    page.current_version = candidate
    if page.contribution == "human":
        page.contribution = "mixed"
    update_fields = ["current_version", "contribution", "updated_at"]
    if page.status != "active":
        page.status = "active"
        update_fields.append("status")
    if candidate.change_type == "qa_answer_candidate":
        page.update_method = "qa_answer"
        update_fields.append("update_method")
    page.save(update_fields=update_fields)
    check.status = "resolved"
    check.save(update_fields=["status", "updated_at"])
    _recount_pending_review(check)
    maintenance = cascade(page.knowledge_base, [page.id], "accept")
    if candidate.build_record_id:
        candidate.build_record.maintenance = maintenance
        candidate.build_record.save(update_fields=["maintenance", "updated_at"])
    return candidate


@transaction.atomic
def decide_check(
    check,
    action,
    operator="",
    body="",
    material=None,
):
    """phase 3 决策中心 API:语义化决策,取代通用 accept/reject。

    Args:
        check: CheckItem 实例
        action: 知识冲突 keep_current/use_new/edit_accept
                页面合并 keep_separate/merge
                (按 check.check_type 自动校验允许集合)
        operator: 决策人
        body: edit_accept 必填,其它动作忽略
        material: use_new / edit_accept 时可选传入新资料以补齐 PageEvidence,
                 缺则从 check.candidate_version 的 build_record/related 推断

    Returns: WikiDecisionRule 写入的规则实例
    Raises:
        ValueError: 错误 action / 空 body / 决策类型不匹配 / 当前版本已过期
    """
    from apps.opspilot.services.wiki.title_service import compact_title_key

    if check.status != "open":
        raise ValueError(f"check not open: status={check.status}")

    # phase 3.1: 决策类型与动作校验
    if check.check_type in ("conflict", "material_update"):
        decision_type = "knowledge_conflict"
        allowed = _KNOWLEDGE_CONFLICT_ACTIONS
    elif check.check_type in ("duplicate", "cannot_merge"):
        decision_type = "page_identity"
        allowed = _PAGE_IDENTITY_ACTIONS
    else:
        raise ValueError(f"check.check_type {check.check_type!r} not in decision-center scope; " "use resolve_check for system-scoped items")
    if action not in allowed:
        raise ValueError(f"action {action!r} not allowed for decision_type {decision_type!r}; allowed={sorted(allowed)}")

    # phase 3.4: 当前版本竞态保护 - 锁必须匹配
    locked_version_id = (check.decision_context or {}).get(_LOCK_KEY)
    if locked_version_id is not None and check.candidate_version_id:
        candidate = check.candidate_version
        # 必须基于 lock 时的 page(取自 candidate.page)
        page = candidate.page
        if page.current_version_id and page.current_version_id != locked_version_id:
            raise ValueError(
                f"check decision outdated: page.current_version_id={page.current_version_id} " f"!= locked={locked_version_id}; refresh before decide"
            )
    else:
        candidate = check.candidate_version
        page = candidate.page if candidate else None

    # phase 3.1 + 3.2: 执行语义化动作 + 写 WikiDecisionRule
    schema_fingerprint = compute_schema_fingerprint(check.knowledge_base)
    subject_key = subject_key_for_page(
        page_type=page.page_type or "concept",
        canonical_title=compact_title_key(page.title or ""),
    )

    # phase 3.2: 提前构造 participants,所有知识冲突决策共用
    # - 优先用调用方传入 material
    # - 否则从 page 已有 PageEvidence 推断当前页面已采纳的 material 集合
    if material is not None and material.id and material.content_hash:
        participants = [{"material_id": material.id, "content_hash": material.content_hash}]
    else:
        evidences = PageEvidence.objects.filter(page=page).select_related("material")
        participants = [
            {"material_id": ev.material_id, "content_hash": ev.material.content_hash}
            for ev in evidences
            if ev.material_id and ev.material.content_hash
        ]

    if decision_type == "knowledge_conflict":
        if action == "keep_current":
            # 当前版本保持,候选版本不删除(供审计),不补证据
            check.status = "resolved"
            check.save(update_fields=["status", "updated_at"])
            result_version = page.current_version
            result_page_id = page.id
            match_extra = {"current_body_hash": _body_hash(page.current_version.body) if page.current_version else ""}
        elif action == "use_new":
            # 候选正文成为新当前版本;原当前版本保留为可恢复历史
            candidate = check.candidate_version
            candidate.is_current = True
            candidate.save(update_fields=["is_current"])
            page.current_version = candidate
            if page.contribution == "human":
                page.contribution = "mixed"
            page.save(update_fields=["current_version", "contribution", "updated_at"])
            check.status = "resolved"
            check.save(update_fields=["status", "updated_at"])
            result_version = candidate
            result_page_id = page.id
            match_extra = {"current_body_hash": _body_hash(candidate.body)}
        elif action == "edit_accept":
            if not body or not body.strip():
                raise ValueError("edit_accept requires non-empty body")
            # 用编辑后正文创建新的当前版本
            new_version = _create_edited_version(page, body, candidate=check.candidate_version)
            new_version.is_current = True
            new_version.save(update_fields=["is_current"])
            page.current_version = new_version
            if page.contribution == "human":
                page.contribution = "mixed"
            page.save(update_fields=["current_version", "contribution", "updated_at"])
            check.status = "resolved"
            check.save(update_fields=["status", "updated_at"])
            result_version = new_version
            result_page_id = page.id
            match_extra = {"current_body_hash": _body_hash(body)}
        else:  # pragma: no cover - 已被 allowed 校验挡掉
            raise ValueError(f"unhandled knowledge_conflict action: {action!r}")

        # 补证据(keep_current 不补,use_new/edit_accept 补)
        if action in ("use_new", "edit_accept") and material is not None:
            _add_evidence_for_decision(page, material, result_version, source="decide_check")

        if not participants:
            # 上下文不完整:不创建规则,check 仍 resolved 但无自动回放能力
            _recount_pending_review(check)
            return None

        _recount_pending_review(check)
        cascade(check.knowledge_base, [result_page_id], "accept")
    else:  # page_identity
        # 页面合并决策由独立 _merge_pages 处理,这里仅校验路径
        raise ValueError("page_identity decisions handled by _merge_pages; not routed here")

    # phase 3.2: 写 WikiDecisionRule(完整 match_snapshot + result_snapshot,审计用)
    rule = create_rule_if_eligible(
        knowledge_base=check.knowledge_base,
        decision_type=decision_type,
        subject_key=subject_key,
        schema_fingerprint=schema_fingerprint,
        participants=participants,
        action=action,
        match_snapshot={
            "participants": participants,
            "schema_fingerprint": schema_fingerprint,
            "policy_version": POLICY_VERSION,
            **match_extra,
        },
        result_snapshot={
            "winner_action": action,
            "body_hash": _body_hash(result_version.body) if result_version else "",
        },
        source_check=check,
        result_page_id=result_page_id,
        result_version=result_version,
    )
    return rule


def _body_hash(body: str) -> str:
    """正文指纹(短哈希,审计/回放前置条件比较用)。"""
    if not body:
        return ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


def _create_edited_version(page, body, candidate):
    """edit_accept:从候选继承 build_record / change_type,创建新当前版本。"""
    last = page.page_versions.order_by("-no").first()
    next_no = (last.no + 1) if last else 1
    return PageVersion.objects.create(
        page=page,
        no=next_no,
        body=body,
        change_type="human_edit",  # 编辑后采用 = 人工编辑
        is_current=False,  # 由 caller 置 True
        build_record=candidate.build_record if candidate else None,
        created_by="human_edit",
        meta_snapshot=(candidate.meta_snapshot if candidate else {}),
    )


def _add_evidence_for_decision(page, material, version, source=""):
    """use_new / edit_accept 补齐 PageEvidence,缺则创建,避免下轮签名缺参与者。"""
    material_version = getattr(material, "current_version", None)
    locator = f"decision:{source}" if source else ""
    # 幂等:同 material + page + locator 已存在则跳过
    exists = PageEvidence.objects.filter(page=page, material=material, locator=locator).exists()
    if exists:
        return
    PageEvidence.objects.create(
        page=page,
        material=material,
        material_version=material_version,
        locator=locator,
    )


def _participants_from_check(check, material=None) -> list:
    """从 check.related + 可选 material 构造参与者集合。

    优先取 related.materials(若已存),否则从 candidate_version 反推,再 fallback material。
    """
    related = check.related or {}
    if isinstance(related, dict):
        mats = related.get("materials") or []
        participants = []
        for m in mats:
            if isinstance(m, dict):
                mat_id = m.get("id")
                content_hash = m.get("content_hash") or ""
            else:
                mat_id = getattr(m, "id", None)
                content_hash = getattr(m, "content_hash", "")
            if mat_id and content_hash:
                participants.append({"material_id": mat_id, "content_hash": content_hash})
        if participants:
            return participants
    # fallback: 用调用方传入的 material
    if material is not None and material.id and material.content_hash:
        return [{"material_id": material.id, "content_hash": material.content_hash}]
    return []


@transaction.atomic
def reject_candidate(check, operator=""):
    """拒绝候选版本:删除候选版本,关闭检查,当前有效版本不变。"""
    candidate = check.candidate_version
    check.status = "dismissed"
    check.candidate_version = None
    check.save(update_fields=["status", "candidate_version", "updated_at"])
    if candidate and not candidate.is_current:
        page = candidate.page
        delete_shell_page = page.current_version_id is None and not page.page_versions.exclude(id=candidate.id).exists()
        candidate.delete()
        if delete_shell_page:
            page.delete()
    _recount_pending_review(check)
    return check


@transaction.atomic
def resolve_check(check, operator="", note=""):
    """将无需候选版本的检查项标记为已处理,并记录处理结果。"""
    if check.status != "open":
        raise ValueError("only open checks can be resolved")
    if check.candidate_version_id:
        raise ValueError("candidate checks must be accepted or rejected")
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["resolution"] = {
        "action": "manual_resolve",
        "operator": operator or "",
        "note": note or "",
        "processed_at": timezone.now().isoformat(),
    }
    check.related = related
    check.status = "resolved"
    check.save(update_fields=["related", "status", "updated_at"])
    _recount_pending_review(check)
    return check


def _related_pages_for_merge(check):
    related = check.related if isinstance(check.related, dict) else {}
    page_ids = related.get("pages", []) or []
    ordered_ids = []
    seen = set()
    for page_id in page_ids:
        try:
            parsed = int(page_id)
        except (TypeError, ValueError):
            continue
        if parsed in seen:
            continue
        ordered_ids.append(parsed)
        seen.add(parsed)
    pages = {
        page.id: page
        for page in KnowledgePage.objects.filter(
            knowledge_base=check.knowledge_base,
            id__in=ordered_ids,
            status="active",
        ).select_related("current_version")
    }
    return [pages[page_id] for page_id in ordered_ids if page_id in pages]


def _merge_target(check, pages):
    related = check.related if isinstance(check.related, dict) else {}
    canonical = (related.get("canonical_title") or "").strip()
    if canonical:
        canonical_key = compact_title_key(canonical)
        for page in pages:
            if compact_title_key(page.title) == canonical_key:
                return page, canonical
    return pages[0], canonical


def _merged_duplicate_body(target, sources):
    pieces = []
    current = (target.current_version.body if target.current_version_id else "") or ""
    if current.strip():
        pieces.append(current.strip())
    for source in sources:
        body = (source.current_version.body if source.current_version_id else "") or ""
        body = body.strip()
        if not body or body in pieces:
            continue
        pieces.append(f"## 合并自: {source.title}\n\n{body}")
    return "\n\n".join(pieces).strip()


def _move_page_evidence(target, sources):
    moved = 0
    for evidence in PageEvidence.objects.filter(page__in=sources):
        exists = PageEvidence.objects.filter(
            page=target,
            material_id=evidence.material_id,
            material_version_id=evidence.material_version_id,
            locator=evidence.locator,
        ).exists()
        if exists:
            evidence.delete()
            continue
        evidence.page = target
        evidence.save(update_fields=["page", "updated_at"])
        moved += 1
    return moved


@transaction.atomic
def merge_duplicate_check(check, operator=""):
    """处理同义/重复页检查:合并到规范标题页,旧页归档并触发增量维护。"""
    if check.check_type != "duplicate":
        raise ValueError("only duplicate checks can be merged")
    if check.status != "open":
        raise ValueError("only open checks can be merged")

    pages = _related_pages_for_merge(check)
    if len(pages) < 2:
        raise ValueError("duplicate check requires at least two active related pages")

    target, canonical = _merge_target(check, pages)
    sources = [page for page in pages if page.id != target.id]
    source_ids = [page.id for page in sources]
    source_titles = [page.title for page in sources]
    body = _merged_duplicate_body(target, sources)
    target.page_versions.filter(is_current=True).update(is_current=False)
    last = target.page_versions.order_by("-no").first()
    version = PageVersion.objects.create(
        page=target,
        no=(last.no + 1) if last else 1,
        body=body,
        change_type="merge_duplicate",
        is_current=True,
        created_by=operator or "",
        meta_snapshot={
            "merged_page_ids": source_ids,
            "merged_titles": source_titles,
            "canonical_title": canonical or target.title,
        },
    )
    if canonical:
        target.title = canonical
    target.current_version = version
    target.tags = list(dict.fromkeys(sum((page.tags or [] for page in pages), [])))
    target.status = "active"
    target.contribution = "mixed"
    target.update_method = "merge_duplicate"
    target.updated_by = operator or ""
    target.save(
        update_fields=[
            "title",
            "tags",
            "current_version",
            "status",
            "contribution",
            "update_method",
            "updated_by",
            "updated_at",
        ]
    )

    for source in sources:
        source.status = "archived"
        source.update_method = "merge_duplicate"
        source.updated_by = operator or ""
        source.save(update_fields=["status", "update_method", "updated_by", "updated_at"])

    moved_evidence = _move_page_evidence(target, sources)
    clear_page_vectors(source_ids)
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["merged_into"] = target.id
    related["archived_pages"] = source_ids
    check.related = related
    check.status = "resolved"
    check.save(update_fields=["related", "status", "updated_at"])
    _recount_pending_review(check)
    maintenance = cascade(
        check.knowledge_base,
        [target.id, *source_ids],
        "merge_duplicate",
        deleted_titles=source_titles,
    )
    return {
        "target_page_id": target.id,
        "archived_page_ids": source_ids,
        "moved_evidence": moved_evidence,
        "maintenance": maintenance,
    }


def scan_health(knowledge_base):
    """系统检查扫描(spec 4.5):孤立、缺有效来源、来源全部失效、过期、疑似重复、冲突、失效关系、低置信度。

    幂等:同类型同页面已存在 open 检查则不重复创建。返回新建的 CheckItem 列表。
    (冲突/低置信为规则启发式;「不符合 Schema」「重要知识缺失」需 schema→类型映射,不在规则扫描内,
    由构建期 cannot_merge 等覆盖无法安全合并类。)
    """
    created = []
    kb = knowledge_base
    pages = list(KnowledgePage.objects.filter(knowledge_base=kb, status="active"))
    by_title = defaultdict(list)
    by_canonical_title = defaultdict(list)
    canonical_titles = {}

    for page in pages:
        has_relation = page.relations_out.exists() or page.relations_in.exists()
        evidences = list(PageEvidence.objects.filter(page=page).select_related("material"))
        has_evidence = bool(evidences)
        by_title[(page.title or "").strip().lower()].append(page)
        canonical = canonical_title(kb, page.title)
        canonical_key = (canonical or "").strip().lower()
        if canonical_key:
            by_canonical_title[canonical_key].append(page)
            canonical_titles[canonical_key] = canonical

        # 孤立:既无关系也无证据
        if not has_relation and not has_evidence:
            created += ensure_check(kb, "orphan", page)
        # 纯 AI 页面无证据 → 缺来源
        elif page.contribution == "ai" and not has_evidence:
            created += ensure_check(kb, "no_source", page)

        # 来源全部失效:有证据但所有证据资料均失效/解析失败
        if has_evidence and all(e.material.status in ("failed", "invalid") for e in evidences):
            created += ensure_check(kb, "all_sources_invalid", page)
        # 过期:证据资料处于「已更新待重建」
        if any(e.material.status == "updated" for e in evidences):
            created += ensure_check(kb, "stale", page)
        # 低置信:AI 页面正文过短
        cur = page.current_version
        if page.contribution == "ai" and cur and len((cur.body or "").strip()) < 30:
            created += ensure_check(kb, "low_confidence", page)

    # 同标题成组:同类型 → 疑似重复;不同类型 → 冲突
    for title, group in by_title.items():
        if not title or len(group) < 2:
            continue
        check_type = "conflict" if len({p.page_type for p in group}) > 1 else "duplicate"
        # 整组同标题页面放进同一条检查的 related,便于在审核详情里并列对比(而非每页一条只看到一页)。
        # ensure_check 幂等:首个页面创建含全组的检查,组内其余页面命中后跳过 → 每组一条。
        group_ids = [p.id for p in group]
        for page in group:
            created += ensure_check(kb, check_type, page, related={"pages": group_ids})

    # 规范标题成组:标题不同但归一到同一 canonical title → 疑似同义重复。
    for canonical_key, group in by_canonical_title.items():
        if not canonical_key or len(group) < 2:
            continue
        title_keys = {(p.title or "").strip().lower() for p in group if (p.title or "").strip()}
        if len(title_keys) < 2:
            continue
        check_type = "conflict" if len({p.page_type for p in group}) > 1 else "duplicate"
        related = {"pages": [p.id for p in group], "canonical_title": canonical_titles[canonical_key]}
        for page in group:
            created += ensure_check(kb, check_type, page, related=related)

    # 失效关系:关系指向非 active 页面
    broken = PageRelation.objects.filter(from_page__knowledge_base=kb).exclude(to_page__status="active").select_related("from_page")
    for rel in broken:
        created += ensure_check(kb, "broken_relation", rel.from_page)

    created += _missing_wikilink_checks(kb, pages)
    created += _graph_insight_checks(kb)
    return created


def _missing_wikilink_checks(knowledge_base, pages):
    active_keys = set()
    for page in pages:
        active_keys.add(normalize_wikilink_key(page.title))
        canonical = canonical_title(knowledge_base, page.title)
        if canonical:
            active_keys.add(normalize_wikilink_key(canonical))

    missing = {}
    for page in pages:
        body = page.current_version.body if page.current_version_id else ""
        for match in LINK_RE.finditer(body or ""):
            target = match.group(1).strip()
            canonical = canonical_title(knowledge_base, target)
            target_keys = {normalize_wikilink_key(target)}
            if canonical:
                target_keys.add(normalize_wikilink_key(canonical))
            target_keys = {key for key in target_keys if key}
            if not target_keys or active_keys & target_keys:
                continue
            target_key = sorted(target_keys)[0]
            item = missing.setdefault(target_key, {"target": canonical or target, "page_ids": set(), "source_titles": set()})
            item["page_ids"].add(page.id)
            item["source_titles"].add(page.title)

    created = []
    for target_key, item in sorted(missing.items()):
        page_ids = sorted(item["page_ids"])
        exists = CheckItem.objects.filter(
            knowledge_base=knowledge_base,
            check_type="missing",
            status="open",
            related__target_key=target_key,
        ).exists()
        if exists or not page_ids:
            continue
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="missing",
                status="open",
                related={
                    "pages": page_ids,
                    "graph_insight": "knowledge_gap",
                    "target": item["target"],
                    "target_key": target_key,
                    "suggested_queries": _missing_suggested_queries(item["target"], item["source_titles"]),
                },
                suggested_actions=["create_page", "supplement_source", "dismiss"],
            )
        )
    return created


def _missing_suggested_queries(target, source_titles):
    queries = []
    target = (target or "").strip()
    if target:
        queries.append(target)
    for title in sorted(source_titles or []):
        title = (title or "").strip()
        if not title or not target:
            continue
        queries.append(f"{title} {target}")
    return list(dict.fromkeys(queries))


def _graph_insight_checks(knowledge_base):
    graph = analyze_graph(knowledge_base)
    insights = graph.get("insights") or {}
    sparse_page_ids = [page_id for community in insights.get("sparse_communities", []) for page_id in community.get("page_ids", []) if page_id]
    cross_edge_page_ids = [page_id for edge in insights.get("cross_community_edges", []) for page_id in (edge.get("from"), edge.get("to")) if page_id]
    pages = {
        page.id: page
        for page in KnowledgePage.objects.filter(
            knowledge_base=knowledge_base,
            status="active",
            id__in=[
                *[item.get("id") for item in insights.get("bridge_nodes", []) if item.get("id")],
                *sparse_page_ids,
                *cross_edge_page_ids,
            ],
        )
    }
    created = []
    for item in insights.get("bridge_nodes", []):
        page = pages.get(item.get("id"))
        if not page:
            continue
        related = {
            "pages": [page.id],
            "graph_insight": "bridge_node",
            "degree": item.get("degree", 0),
            "component_count_after_removal": item.get("component_count_after_removal", 0),
        }
        created += ensure_check(
            knowledge_base,
            "bridge_node",
            page,
            suggested_actions=["review_graph", "supplement_source", "restructure_page"],
            related=related,
        )
    for item in insights.get("cross_community_edges", []):
        page_ids = sorted(page_id for page_id in [item.get("from"), item.get("to")] if page_id in pages)
        if len(page_ids) != 2:
            continue
        exists = CheckItem.objects.filter(
            knowledge_base=knowledge_base,
            check_type="cross_community_edge",
            status="open",
            related__pages__contains=page_ids,
        ).exists()
        if exists:
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "cross_community_edge",
            "from": item.get("from"),
            "to": item.get("to"),
            "from_title": item.get("from_title", ""),
            "to_title": item.get("to_title", ""),
            "weight": item.get("weight", 0),
            "signals": item.get("signals", {}),
            "from_community": item.get("from_community", -1),
            "to_community": item.get("to_community", -1),
        }
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="cross_community_edge",
                status="open",
                related=related,
                suggested_actions=["review_graph", "supplement_source", "restructure_page"],
            )
        )
    for item in insights.get("sparse_communities", []):
        page_ids = [page_id for page_id in item.get("page_ids", []) if page_id in pages]
        if not page_ids:
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "sparse_community",
            "density": item.get("density", 0),
            "edge_count": item.get("edge_count", 0),
            "possible_edges": item.get("possible_edges", 0),
        }
        created += ensure_check(
            knowledge_base,
            "sparse_community",
            pages[page_ids[0]],
            suggested_actions=["review_graph", "supplement_source", "restructure_page"],
            related=related,
        )
    # 惊奇连接:跨社区强边且两侧标题不共享显著词
    for item in insights.get("surprise_links", []):
        page_ids = sorted(page_id for page_id in [item.get("from"), item.get("to")] if page_id in pages)
        if len(page_ids) != 2:
            continue
        exists = CheckItem.objects.filter(
            knowledge_base=knowledge_base,
            check_type="surprise_link",
            status="open",
            related__pages__contains=page_ids,
        ).exists()
        if exists:
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "surprise_link",
            "from": item.get("from"),
            "to": item.get("to"),
            "from_title": item.get("from_title", ""),
            "to_title": item.get("to_title", ""),
            "weight": item.get("weight", 0),
            "signals": item.get("signals", {}),
            "from_community": item.get("from_community", -1),
            "to_community": item.get("to_community", -1),
        }
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="surprise_link",
                status="open",
                related=related,
                suggested_actions=["review_graph", "restructure_page", "supplement_source"],
            )
        )
    return created


def ensure_check(knowledge_base, check_type, page, suggested_actions=None, related=None):
    """幂等创建检查事项:同库同类型同页面已有 open 检查则不重复。返回新建列表。

    related 可显式传入(如重复/冲突整组页面);缺省为仅本页 {"pages": [page.id]}。
    """
    exists = CheckItem.objects.filter(
        knowledge_base=knowledge_base, check_type=check_type, status="open", related__pages__contains=[page.id]
    ).exists()
    if exists:
        return []
    return [
        CheckItem.objects.create(
            knowledge_base=knowledge_base,
            check_type=check_type,
            status="open",
            related=related or {"pages": [page.id]},
            suggested_actions=suggested_actions or ["dismiss", "supplement_source"],
        )
    ]
