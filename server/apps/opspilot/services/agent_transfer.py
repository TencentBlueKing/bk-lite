import io
import json
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml
from django.db import transaction

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMSkill, SkillPackage, SkillTools
from apps.opspilot.services.asset_tags import normalize_user_tags
from apps.opspilot.services.skill_package.importer import SkillPackageImporter
from apps.opspilot.utils.skill_tool_log import log_skill_tools_replaced

KIND = "opspilot-agent"
FORMAT_VERSION = 1
_TRANSPORTS = {"streamable_http", "sse"}
_KWARG_TYPES = {"text", "textarea", "password", "number", "checkbox"}
MAX_AGENT_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_AGENT_ENTRIES = 128
MAX_AGENT_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
MAX_PACKAGE_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_ENTRIES = 2000
MAX_PACKAGE_UNCOMPRESSED_BYTES = 64 * 1024 * 1024


class AgentArchiveError(Exception):
    pass


class _ZipBudget:
    """按成员声明大小和实际读出的字节数共用一个上界。"""

    def __init__(self, archive: zipfile.ZipFile, limit: int, label: str):
        self.archive = archive
        self.left = limit
        self.label = label
        self._cache: dict[str, bytes] = {}

    def read(self, member) -> bytes:
        info = member if isinstance(member, zipfile.ZipInfo) else self.archive.getinfo(member)
        cached = self._cache.get(info.filename)
        if cached is not None:
            return cached
        if info.file_size < 0 or info.file_size > self.left:
            raise AgentArchiveError(f"{self.label}解压后超过大小限制")
        with self.archive.open(info, "r") as handle:
            data = handle.read(self.left + 1)
        if len(data) > self.left:
            raise AgentArchiveError(f"{self.label}解压后超过大小限制")
        self.left -= len(data)
        self._cache[info.filename] = data
        return data


def _guard_zip_headers(archive: zipfile.ZipFile, *, entries: int, uncompressed: int, label: str) -> None:
    infos = archive.infolist()
    if len(infos) > entries:
        raise AgentArchiveError(f"{label}条目过多")
    total = 0
    for info in infos:
        if info.is_dir():
            continue
        size = info.file_size
        if size < 0 or size > uncompressed or total > uncompressed - size:
            raise AgentArchiveError(f"{label}解压后超过大小限制")
        total += size


def _inspect_package_blob(data: bytes) -> None:
    if len(data) > MAX_PACKAGE_ARCHIVE_BYTES:
        raise AgentArchiveError("技能包超过大小限制")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return
    with archive:
        _guard_zip_headers(
            archive,
            entries=MAX_PACKAGE_ENTRIES,
            uncompressed=MAX_PACKAGE_UNCOMPRESSED_BYTES,
            label="技能包",
        )


def read_bounded_upload(upload) -> bytes:
    if upload is None:
        return b""
    claimed = getattr(upload, "size", None)
    try:
        claimed_size = int(claimed)
    except (TypeError, ValueError):
        claimed_size = None
    if claimed_size is not None and claimed_size > MAX_AGENT_ARCHIVE_BYTES:
        raise AgentArchiveError("智能体文件超过大小限制")
    data = upload.read(MAX_AGENT_ARCHIVE_BYTES + 1)
    if len(data) > MAX_AGENT_ARCHIVE_BYTES:
        raise AgentArchiveError("智能体文件超过大小限制")
    return data


@dataclass
class StoredSkillPackage:
    package_id: str
    name: str
    version: str
    description: str
    category: str
    required_tools: list[str]
    triggers: list[str]
    storage_path: Path
    manifest: dict
    skill_markdown: str


@dataclass
class AgentRecipe:
    name: str
    introduction: str
    skill_prompt: str
    guide: str
    skill_params: list[dict] = field(default_factory=list)
    conversation_window_size: int = 10
    run_model_call_limit: int = 10
    builtin_tools: list[str] = field(default_factory=list)
    builtin_packages: list[str] = field(default_factory=list)
    packages: list[tuple[str, bytes]] = field(default_factory=list)
    omitted_packages: list[str] = field(default_factory=list)
    omitted_tools: list[str] = field(default_factory=list)
    mcp: list[dict] = field(default_factory=list)

    @property
    def needs_tool_add(self) -> bool:
        return bool(self.packages or self.mcp)


def permission_denied_message(user, code: str) -> str | None:
    if getattr(user, "is_superuser", False):
        return None
    perms = getattr(user, "permission", None)
    if isinstance(perms, dict):
        owned = set(perms.get("opspilot") or [])
    elif isinstance(perms, set):
        owned = perms
    else:
        owned = set()
    if code in owned:
        return None
    return {
        "skill_setting-Edit": "缺少设置编辑权限",
        "skill_list-Add": "缺少新建智能体权限",
        "tool_list-Add": "缺少工具新增权限",
    }[code]


def build_agent_zip(skill: LLMSkill) -> bytes:
    document, blobs = _export_document(skill)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("agent.json", json.dumps(document, ensure_ascii=False))
        for index, blob in enumerate(blobs):
            archive.writestr(f"packages/{index}.zip", blob)
    payload = buffer.getvalue()
    if len(payload) > MAX_AGENT_ARCHIVE_BYTES:
        raise AgentArchiveError("智能体文件超过大小限制")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        _guard_zip_headers(
            archive,
            entries=MAX_AGENT_ENTRIES,
            uncompressed=MAX_AGENT_UNCOMPRESSED_BYTES,
            label="智能体文件",
        )
    return payload


def read_agent_zip(data: bytes) -> AgentRecipe | None:
    if not data:
        return None
    if len(data) > MAX_AGENT_ARCHIVE_BYTES:
        raise AgentArchiveError("智能体文件超过大小限制")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None
    with archive:
        _guard_zip_headers(
            archive,
            entries=MAX_AGENT_ENTRIES,
            uncompressed=MAX_AGENT_UNCOMPRESSED_BYTES,
            label="智能体文件",
        )
        budget = _ZipBudget(archive, MAX_AGENT_UNCOMPRESSED_BYTES, "智能体文件")
        document = _find_document(archive, budget)
        if document is None:
            return None
        packages: list[tuple[str, bytes]] = []
        for item in document.get("packages") or []:
            if not isinstance(item, dict):
                continue
            source_name = str(item.get("source_name") or "")
            member = str(item.get("archive") or "")
            try:
                info = archive.getinfo(member)
            except KeyError:
                packages.append((source_name, b""))
                continue
            if info.file_size > MAX_PACKAGE_ARCHIVE_BYTES:
                raise AgentArchiveError("技能包超过大小限制")
            blob = budget.read(info)
            _inspect_package_blob(blob)
            packages.append((source_name, blob))
        return AgentRecipe(
            name=str(document.get("name") or ""),
            introduction=str(document.get("introduction") or ""),
            skill_prompt=str(document.get("skill_prompt") or ""),
            guide=str(document.get("guide") or ""),
            skill_params=_public_params(document.get("skill_params")),
            conversation_window_size=_positive_int(document.get("conversation_window_size"), 10),
            run_model_call_limit=_call_limit(document.get("run_model_call_limit")),
            builtin_tools=_string_list(document.get("builtin_tools")),
            builtin_packages=_string_list(document.get("builtin_packages")),
            packages=packages,
            omitted_packages=_string_list(document.get("omitted_packages")),
            omitted_tools=_string_list(document.get("omitted_tools")),
            mcp=_mcp_entries(document.get("mcp")),
        )


def missing_builtin_message(recipe: AgentRecipe) -> str | None:
    missing_tools = [name for name in recipe.builtin_tools if not SkillTools.objects.filter(name=name, is_build_in=True).exists()]
    missing_packages = [
        package_id for package_id in recipe.builtin_packages if not SkillPackage.objects.filter(package_id=package_id, is_build_in=True).exists()
    ]
    parts = []
    if missing_tools:
        parts.append(f"当前版本缺少相关工具：{'、'.join(missing_tools)}。")
    if missing_packages:
        parts.append(f"当前版本缺少相关技能包：{'、'.join(missing_packages)}。")
    if not parts:
        return None
    return "".join(parts) + "请升级版本。"


def import_agent_recipe(recipe: AgentRecipe, *, team_id: int, user, name_taken) -> dict:
    notes: list[str] = []
    final_name, renamed = _allocate_name(recipe.name, name_taken)
    if renamed:
        notes.append(f"名称已调整为「{final_name}」")
    skill_params = _import_params(recipe.skill_params, notes)
    domain = getattr(user, "domain", None) or "domain.com"
    username = getattr(user, "username", "") or ""
    for source_name in recipe.omitted_packages:
        notes.append(f"技能包「{source_name or '技能包'}」没有带上")
    for source_name in recipe.omitted_tools:
        notes.append(f"工具「{source_name or '工具'}」没有带上")

    with transaction.atomic():
        return _create_imported_skill(
            recipe,
            final_name=final_name,
            skill_params=skill_params,
            team_id=team_id,
            domain=domain,
            username=username,
            notes=notes,
        )


def _create_imported_skill(recipe, *, final_name, skill_params, team_id, domain, username, notes) -> dict:
    skill = LLMSkill.objects.create(
        name=final_name,
        introduction=recipe.introduction,
        skill_prompt=recipe.skill_prompt,
        guide=recipe.guide,
        skill_params=skill_params,
        conversation_window_size=recipe.conversation_window_size,
        run_model_call_limit=recipe.run_model_call_limit,
        enable_conversation_history=True,
        team=[team_id],
        usage_team=[team_id],
        skill_package_params={},
        created_by=username[:32],
        updated_by=username[:32],
        domain=domain,
        updated_by_domain=domain,
    )
    packages = _import_packages(recipe, skill_domain=domain, team_id=team_id, username=username, notes=notes)
    tools = _import_tools(recipe, team_id=team_id, domain=domain, username=username, notes=notes)
    skill.skill_packages = packages
    skill.tools = tools
    skill.save(update_fields=["skill_packages", "tools"])
    log_skill_tools_replaced(skill_id=skill.id, actor=username, before=[], after=tools)
    return {"id": skill.id, "name": skill.name, "notes": notes}


def _export_document(skill: LLMSkill) -> tuple[dict, list[bytes]]:
    builtin_tools: list[str] = []
    omitted_tools: list[str] = []
    mcp: list[dict] = []
    for binding in skill.tools or []:
        if not isinstance(binding, dict):
            continue
        row = _tool_row(binding, skill)
        if row is not None and row.is_build_in:
            if row.name:
                builtin_tools.append(row.name)
            continue
        if row is None:
            name = str(binding.get("name") or "")
            if name:
                omitted_tools.append(name)
            continue
        params = row.params or {}
        transport = params.get("transport") or "sse"
        mcp.append(
            _mcp_entry(
                {
                    "name": row.name,
                    "url": str(params.get("url") or ""),
                    "transport": transport,
                    "auth_required": bool(params.get("enable_auth")),
                    "description": row.description or "",
                    "kwargs": params.get("kwargs"),
                    "user_tags": row.user_tags or row.tags,
                }
            )
        )

    builtin_packages: list[str] = []
    package_entries: list[dict] = []
    omitted: list[str] = []
    blobs: list[bytes] = []
    for binding in skill.skill_packages or []:
        if not isinstance(binding, dict):
            continue
        row = _package_row(binding, skill.domain)
        label = _package_label(binding, row)
        if row is not None and row.is_build_in:
            builtin_packages.append(row.package_id)
            continue
        archive = _package_archive(row)
        if archive is None:
            omitted.append(label)
            continue
        package_entries.append({"archive": f"packages/{len(blobs)}.zip", "source_name": label})
        blobs.append(archive)

    document = {
        "kind": KIND,
        "format_version": FORMAT_VERSION,
        "name": skill.name,
        "introduction": skill.introduction or "",
        "skill_prompt": skill.skill_prompt or "",
        "guide": skill.guide or "",
        "skill_params": _export_params(skill.skill_params),
        "conversation_window_size": skill.conversation_window_size,
        "run_model_call_limit": skill.run_model_call_limit,
        "builtin_tools": _dedupe(builtin_tools),
        "builtin_packages": _dedupe(builtin_packages),
        "packages": package_entries,
        "omitted_packages": omitted,
        "omitted_tools": _dedupe(omitted_tools),
        "mcp": mcp,
    }
    return document, blobs


def _find_document(archive: zipfile.ZipFile, budget: _ZipBudget) -> dict | None:
    for info in archive.infolist():
        if PurePosixPath(info.filename).name != "agent.json" or info.is_dir():
            continue
        try:
            parsed = json.loads(budget.read(info).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict) and parsed.get("kind") == KIND and parsed.get("format_version") == FORMAT_VERSION:
            return parsed
    return None


def _export_params(params) -> list[dict]:
    exported = []
    for item in params or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        param_type = item.get("type") or "text"
        value = "" if param_type == "password" else item.get("value") or ""
        exported.append({"key": str(item["key"]), "type": str(param_type), "value": value if isinstance(value, str) else ""})
    return exported


def _public_params(params) -> list[dict]:
    exported = []
    for item in params or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        param_type = str(item.get("type") or "text")
        value = "" if param_type == "password" else item.get("value") or ""
        exported.append({"key": str(item["key"]), "type": param_type, "value": value if isinstance(value, str) else ""})
    return exported


def _import_params(params: list[dict], notes: list[str]) -> list[dict]:
    imported = []
    for item in params:
        if item.get("type") == "password":
            notes.append(f"提示词参数「{item['key']}」需要补全")
            imported.append({"key": item["key"], "type": "password", "value": ""})
        else:
            imported.append({"key": item["key"], "type": item.get("type") or "text", "value": item.get("value") or ""})
    return imported


def _import_packages(recipe: AgentRecipe, *, skill_domain: str, team_id: int, username: str, notes: list[str]) -> list[dict]:
    bindings = []
    for source_name, blob in recipe.packages:
        stored = save_package_copy(blob, str(team_id))
        if stored is None:
            notes.append(f"技能包「{source_name or '技能包'}」没有带上")
            continue
        package_name, renamed = _allocate_package_name(stored.name, skill_domain)
        if renamed:
            notes.append(f"技能包「{stored.name}」已保存为「{package_name}」")
        manifest = dict(stored.manifest or {})
        manifest["name"] = package_name
        row = SkillPackage.objects.create(
            package_id=stored.package_id,
            name=package_name,
            version=stored.version,
            description=stored.description,
            category=stored.category,
            source_type="zip",
            storage_path=str(stored.storage_path),
            manifest=manifest,
            skill_markdown=stored.skill_markdown,
            required_tools=stored.required_tools,
            triggers=stored.triggers,
            team=[team_id],
            is_build_in=False,
            created_by=username[:32],
            updated_by=username[:32],
            domain=skill_domain,
            updated_by_domain=skill_domain,
        )
        bindings.append(_package_binding(row))
    for package_id in recipe.builtin_packages:
        row = SkillPackage.objects.filter(package_id=package_id, is_build_in=True).first()
        if row is not None:
            bindings.append(_package_binding(row))
    return bindings


def _import_tools(recipe: AgentRecipe, *, team_id: int, domain: str, username: str, notes: list[str]) -> list[dict]:
    tools = []
    for name in recipe.builtin_tools:
        row = SkillTools.objects.filter(name=name, is_build_in=True).first()
        if row is not None:
            tools.append({"id": row.id, "name": row.name, "icon": row.icon or "", "kwargs": []})
    for entry in recipe.mcp:
        url = str(entry.get("url") or "").strip()
        source_name = str(entry.get("name") or "mcp")
        if not url:
            notes.append(f"MCP「{source_name}」没有带上链接")
            continue
        tool_name, renamed = _allocate_tool_name(source_name)
        transport = entry.get("transport") or "sse"
        row = SkillTools.objects.create(
            name=tool_name,
            description=str(entry.get("description") or ""),
            user_tags=normalize_user_tags(entry.get("user_tags")),
            params={
                "url": url,
                "transport": transport if transport in _TRANSPORTS else "sse",
                "kwargs": _mcp_kwargs(entry.get("kwargs")),
                "enable_auth": False,
                "auth_token": "",
            },
            team=[team_id],
            is_build_in=False,
            created_by=username[:32],
            updated_by=username[:32],
            domain=domain,
            updated_by_domain=domain,
        )
        tools.append({"id": row.id, "name": row.name, "icon": row.icon or "", "kwargs": []})
        if renamed:
            notes.append(f"MCP「{source_name}」已保存为「{tool_name}」")
        if entry.get("auth_required"):
            notes.append(f"MCP「{tool_name}」缺少凭据，请到工具页补全")
    return tools


def save_package_copy(data: bytes, organization_id: str) -> StoredSkillPackage | None:
    if not data:
        return None
    _inspect_package_blob(data)
    storage_path: Path | None = None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            budget = _ZipBudget(archive, MAX_PACKAGE_UNCOMPRESSED_BYTES, "技能包")
            SkillPackageImporter._validate_members(members)
            skill_doc_member = SkillPackageImporter._find_required_member(members, "SKILL.md")
            package_root = PurePosixPath(skill_doc_member).parent
            manifest_member = SkillPackageImporter._find_optional_member(members, "skill.yaml", package_root)
            skill_markdown = budget.read(skill_doc_member).decode("utf-8")
            frontmatter, skill_body = SkillPackageImporter._split_frontmatter(skill_markdown)
            if manifest_member:
                manifest = SkillPackageImporter._load_manifest(
                    budget.read(manifest_member).decode("utf-8"),
                    source="skill.yaml",
                )
            elif frontmatter:
                manifest = SkillPackageImporter._load_manifest(frontmatter, source="SKILL.md frontmatter")
            else:
                manifest = {}
            version = SkillPackageImporter._sanitize_version(str(manifest.get("version") or "0.1.0"))
            name = str(manifest.get("name") or SkillPackageImporter._extract_markdown_title(skill_body) or "skill-package")
            package_id = uuid.uuid4().hex
            storage_path = SkillPackageImporter().storage_root / organization_id / package_id / version
            if storage_path.exists():
                return None
            extracted = storage_path / "extracted"
            extracted.mkdir(parents=True)
            (storage_path / "original.zip").write_bytes(data)
            for member in members:
                relative_name = SkillPackageImporter._relative_member_name(member.filename, package_root)
                if not relative_name:
                    continue
                target = extracted / relative_name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(budget.read(member))
    except AgentArchiveError:
        if storage_path is not None and storage_path.exists():
            shutil.rmtree(storage_path, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, ValueError, OSError, UnicodeDecodeError) as exc:
        if storage_path is not None and storage_path.exists():
            shutil.rmtree(storage_path, ignore_errors=True)
        logger.debug("agent import skipped unreadable skill package error_type=%s", type(exc).__name__)
        return None
    return StoredSkillPackage(
        package_id=package_id,
        name=name,
        version=version,
        description=str(manifest.get("description") or ""),
        category=str(manifest.get("category") or ""),
        required_tools=SkillPackageImporter._string_list(manifest.get("required_tools")),
        triggers=SkillPackageImporter._string_list(manifest.get("triggers")),
        storage_path=storage_path,
        manifest=manifest,
        skill_markdown=skill_body,
    )


def _id_set(values) -> set:
    found = set()
    for value in values or []:
        if value in (None, ""):
            continue
        found.add(value)
        found.add(str(value))
        try:
            found.add(int(value))
        except (TypeError, ValueError):
            pass
    return found


def _tool_in_scope(row, skill: LLMSkill) -> bool:
    if row.is_build_in:
        return True
    if (row.domain or "") != (skill.domain or ""):
        return False
    if not row.team:
        return True
    return bool(_id_set(row.team) & _id_set(skill.team))


def _tool_row(binding: dict, skill: LLMSkill):
    name = str(binding.get("name") or "")
    pk = binding.get("id")
    if pk:
        row = SkillTools.objects.filter(pk=pk).first()
        if row is not None and _tool_in_scope(row, skill) and (not name or row.name == name):
            return row
    if name:
        row = SkillTools.objects.filter(name=name).first()
        if row is not None and _tool_in_scope(row, skill):
            return row
    return None


def _package_identifiers(row) -> set[str]:
    found = set()
    if row.package_id:
        found.add(str(row.package_id))
    manifest = row.manifest if isinstance(row.manifest, dict) else {}
    manifest_id = manifest.get("id")
    if manifest_id:
        found.add(str(manifest_id))
    return found


def _package_identity_matches(row, binding: dict) -> bool:
    package_id = str(binding.get("package_id") or "")
    name = str(binding.get("name") or "")
    if package_id and package_id in _package_identifiers(row):
        return True
    return bool(name) and name == (row.name or "")


def _package_row(binding: dict, domain: str):
    pk = binding.get("id")
    if pk:
        row = SkillPackage.objects.filter(pk=pk, domain=domain or "").first()
        if row is not None and _package_identity_matches(row, binding):
            return row
    package_id = str(binding.get("package_id") or "")
    version = binding.get("version")
    if package_id:
        found = _package_by_column_id(package_id, version, domain)
        if found is not None:
            return found
        # 页面导入把清单 id 写进 package_id。智能体导入另存后这一列变成 uuid，清单 id 留在 manifest。
        found = _package_by_manifest_id(package_id, version, domain, binding.get("name"))
        if found is not None:
            return found
    name = str(binding.get("name") or "")
    if name and domain:
        return _named_package(name, version, domain)
    return None


def _package_by_column_id(package_id: str, version, domain: str):
    queryset = SkillPackage.objects.filter(package_id=package_id)
    if version:
        queryset = queryset.filter(version=version)
    if domain:
        scoped = queryset.filter(domain=domain).first()
        if scoped is not None:
            return scoped
    # 内置包按包标识匹配目录，正文不进 ZIP。自定义包不跨域。
    return queryset.filter(is_build_in=True).first()


def _package_by_manifest_id(package_id: str, version, domain: str, name):
    queryset = SkillPackage.objects.filter(manifest__id=package_id, domain=domain or "")
    if name:
        named = queryset.filter(name=name)
        if version:
            versioned = named.filter(version=version)
            if versioned.exists():
                named = versioned
        chosen = named.first()
        if chosen is not None:
            return chosen
    if version:
        versioned = queryset.filter(version=version).first()
        if versioned is not None:
            return versioned
    return queryset.first()


def _named_package(name: str, version, domain: str):
    queryset = SkillPackage.objects.filter(name=name, domain=domain, is_build_in=False)
    if version:
        versioned = queryset.filter(version=version).first()
        if versioned is not None:
            return versioned
    return queryset.first()


def _package_archive(row) -> bytes | None:
    original = _original_zip(row)
    if original is not None:
        _inspect_package_blob(original)
        return original
    if row is None or not str(row.skill_markdown or "").strip():
        return None
    blob = _zip_stored_skill(row)
    _inspect_package_blob(blob)
    return blob


def _zip_stored_skill(row) -> bytes:
    body = str(row.skill_markdown or "")
    if not body.startswith("---"):
        manifest = {
            "name": row.name or "技能包",
            "description": row.description or "",
            "version": row.version or "0.1.0",
        }
        if row.triggers:
            manifest["triggers"] = list(row.triggers)
        if row.required_tools:
            manifest["required_tools"] = list(row.required_tools)
        front = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False).strip()
        body = f"---\n{front}\n---\n\n{body}"
    slug = SkillPackageImporter._sanitize_id(row.name or "skill")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{slug}/SKILL.md", body)
    return buffer.getvalue()


def _allocate_package_name(base: str, domain: str) -> tuple[str, bool]:
    cleaned = ((base or "").strip() or "技能包")[:255]

    def taken(name: str) -> bool:
        return SkillPackage.objects.filter(name=name, domain=domain).exists()

    if not taken(cleaned):
        return cleaned, False
    index = 2
    while index <= 1000:
        suffix = f" {index}"
        candidate = cleaned[: 255 - len(suffix)] + suffix
        if not taken(candidate):
            return candidate, True
        index += 1
    return cleaned[:240] + f" {index}", True


def _original_zip(row) -> bytes | None:
    if row is None or not row.storage_path:
        return None
    candidate = Path(row.storage_path) / "original.zip"
    if not candidate.is_file():
        return None
    with candidate.open("rb") as handle:
        data = handle.read(MAX_PACKAGE_ARCHIVE_BYTES + 1)
    if len(data) > MAX_PACKAGE_ARCHIVE_BYTES:
        raise AgentArchiveError("技能包超过大小限制")
    return data


def _package_label(binding: dict, row) -> str:
    if row is not None and row.name:
        return row.name
    return str(binding.get("name") or binding.get("package_id") or "技能包")


def _package_binding(row: SkillPackage) -> dict:
    return {
        "id": row.id,
        "package_id": row.package_id,
        "name": row.name,
        "version": row.version,
        "description": row.description,
        "category": row.category,
        "required_tools": row.required_tools or [],
        "triggers": row.triggers or [],
    }


def _allocate_name(base: str, taken) -> tuple[str, bool]:
    cleaned = (base or "").strip() or "智能体"
    if not taken(cleaned):
        return cleaned, False
    index = 2
    while index <= 1000:
        candidate = f"{cleaned} {index}"
        if not taken(candidate):
            return candidate, True
        index += 1
    return f"{cleaned} {index}", True


def _allocate_tool_name(base: str) -> tuple[str, bool]:
    cleaned = (base or "").strip() or "mcp"
    cleaned = cleaned[:100]
    if not SkillTools.objects.filter(name=cleaned).exists():
        return cleaned, False
    index = 2
    while index <= 1000:
        suffix = f" {index}"
        candidate = cleaned[: 100 - len(suffix)] + suffix
        if not SkillTools.objects.filter(name=candidate).exists():
            return candidate, True
        index += 1
    return cleaned[:90] + f" {index}", True


def _positive_int(value, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _call_limit(value) -> int:
    number = _positive_int(value, 10)
    if 1 <= number <= 100:
        return number
    return 10


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe([str(item) for item in value if isinstance(item, str) and item])


def _mcp_kwargs(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        kind = item.get("type") or "text"
        cleaned.append(
            {
                "key": key,
                "type": kind if kind in _KWARG_TYPES else "text",
                "isRequired": bool(item.get("isRequired")),
                "value": "",
            }
        )
    return cleaned


def _mcp_entry(item: dict) -> dict:
    transport = item.get("transport") or "sse"
    return {
        "name": str(item.get("name") or ""),
        "url": str(item.get("url") or ""),
        "transport": transport if transport in _TRANSPORTS else "sse",
        "auth_required": bool(item.get("auth_required")),
        "description": str(item.get("description") or ""),
        "kwargs": _mcp_kwargs(item.get("kwargs")),
        "user_tags": normalize_user_tags(item.get("user_tags")),
    }


def _mcp_entries(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [_mcp_entry(item) for item in value if isinstance(item, dict)]


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
