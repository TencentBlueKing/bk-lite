"""SkillPackage → SKILL.md 物化器。

将数据库中的 SkillPackage（或等价的 dict）渲染成符合 deepagents Agent Skills
规范的 SKILL.md 文件，并写入任意 deepagents BackendProtocol 后端，目录布局：

    /skills/<name>/SKILL.md
    /skills/<name>/scripts/...
    /skills/<name>/references/...
    /skills/<name>/assets/...
    /skills/<name>/bin/...

SKILL.md 由 YAML frontmatter（name + description）加 markdown 正文组成：
- name：小写、仅含字母数字与连字符，长度 <= 64
- description：长度 <= 1024

**资源真相源是磁盘上的 extracted_root**（由 hydrate_skill_packages 注入），
本物化器对附属资源采用流式读盘（Path.rglob 扫描按需 read_text / read_bytes），
不在 snapshot 里复制文件内容，避免 mb 级包占用内存。

设计上保持后端无关：文本走 ``backend.write``，二进制走 ``backend.upload_files``。
backend 是 deepagents BackendProtocol 抽象（Phase 1 将 LocalShellBackend
替换为 NATS worker / 容器沙箱），调用方不变。
"""
from __future__ import annotations

import re
import stat
from pathlib import Path
from posixpath import normpath
from typing import Any

import yaml

from apps.core.logger import opspilot_logger as logger

# Agent Skills 规范约束
NAME_MAX_LEN = 64
DESCRIPTION_MAX_LEN = 1024
SKILLS_ROOT = "/skills"
# 允许从 package 中复制的附属资源子目录（dict 后向兼容路径仍用这三项）
ASSET_DIRS = ("scripts", "references", "assets")
# 根级清单文件由 render_skill_md 处理，不原样拷贝
_SKIP_ROOT_FILES = frozenset({"SKILL.md", "skill.yaml"})
_EXEC_MASK = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def _get(package: Any, key: str, default: Any = None) -> Any:
    """兼容 dict 与对象两种 package 形态的取值。"""
    if isinstance(package, dict):
        return package.get(key, default)
    return getattr(package, key, default)


def sanitize_skill_name(raw: Any) -> str:
    """把任意字符串规整为合法的 skill name。

    规则：转小写 -> 非 [a-z0-9] 字符折叠为单个连字符 -> 去除首尾连字符
    -> 截断到 64 字符 -> 再次去除尾部连字符。空结果回退为 ``skill``。
    """
    text = str(raw or "").lower()
    # 非法字符（含空格、下划线、unicode 等）统一折叠为连字符
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) > NAME_MAX_LEN:
        text = text[:NAME_MAX_LEN].rstrip("-")
    return text or "skill"


def _build_description(package: Any) -> str:
    manifest = _get(package, "manifest", None) or {}
    if isinstance(manifest, dict):
        base = manifest.get("description") or _get(package, "description", "") or ""
    else:
        base = _get(package, "description", "") or ""
    base = str(base).strip()

    triggers = _get(package, "triggers", None) or []
    if isinstance(triggers, str):
        triggers = [triggers]
    trigger_words = [str(t).strip() for t in triggers if str(t).strip()]
    if trigger_words:
        suffix = "触发词: " + ", ".join(trigger_words)
        base = f"{base} {suffix}".strip() if base else suffix

    if len(base) > DESCRIPTION_MAX_LEN:
        base = base[:DESCRIPTION_MAX_LEN]
    return base


def render_skill_md(package: Any) -> str:
    """渲染 SKILL.md 字符串（纯函数，无 IO）。"""
    name = sanitize_skill_name(_get(package, "package_id", None) or _get(package, "name", None))
    description = _build_description(package)
    body = str(_get(package, "skill_markdown", "") or "").strip()

    frontmatter = yaml.safe_dump(
        {"name": name, "description": description},
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return f"---\n{frontmatter}---\n\n{body}\n"


def _safe_join(base: str, rel: str) -> str | None:
    """把相对路径安全拼接到 base 下，拒绝越界 / 绝对路径。"""
    rel = str(rel or "").strip()
    if not rel or rel.startswith("/"):
        return None
    joined = normpath(f"{base}/{rel}")
    prefix = base.rstrip("/") + "/"
    if not joined.startswith(prefix):
        return None
    return joined


def _is_executable(path: Path) -> bool:
    try:
        return bool(path.stat().st_mode & _EXEC_MASK)
    except OSError:
        return False


def _chmod_executable(backend: Any, target: str) -> None:
    chmod = getattr(backend, "chmod", None)
    if callable(chmod):
        try:
            chmod(target, 0o755)
            return
        except Exception as exc:
            logger.warning("技能资源 chmod 失败(%s): %r", target, exc)
            return
    execute = getattr(backend, "execute", None)
    if callable(execute):
        try:
            execute(f"chmod 755 {target}")
        except Exception as exc:
            logger.warning("技能资源 chmod 失败(%s): %r", target, exc)


def _write_extracted_file(backend: Any, target: str, file: Path, name: str, rel: str) -> bool:
    """文本走 write，二进制回退 upload_files；源文件带执行位则补 chmod。"""
    try:
        try:
            content = file.read_text(encoding="utf-8")
            backend.write(target, content)
        except Exception:
            raw = file.read_bytes()
            upload = getattr(backend, "upload_files", None)
            if not callable(upload):
                logger.warning("技能资源跳过二进制(%s/%s): 后端无 upload_files", name, rel)
                return False
            upload([(target, raw)])
        if _is_executable(file):
            _chmod_executable(backend, target)
        return True
    except Exception as exc:
        logger.warning("技能资源写入失败(%s/%s): %r", name, rel, exc)
        return False


def materialize_skill_package(package: Any, backend: Any, skills_root: str = SKILLS_ROOT) -> list[str]:
    """把 package 物化为后端中的 SKILL.md 与附属资源，返回写入的路径列表。

    Args:
        package: SkillPackage（或等价 dict）。
        backend: 任意 deepagents BackendProtocol 后端（``write`` / ``upload_files``）。
        skills_root: 技能目录父路径。默认 ``/skills``；当后端使用真实主机路径
            （如 ``LocalShellBackend(virtual_mode=False)``）时，传入工作目录下的
            绝对路径（如 ``{root_dir}/skills``）以避免写到主机根目录。

    资源路径分支：
        - **流式路径（新）**：package 含 ``extracted_root: Path``，扫描整个
          extracted/（排除根级 SKILL.md / skill.yaml），文本 write、二进制
          upload_files。
        - **dict 路径（旧/后向兼容）**：package 含 ``scripts``/``references``/``assets``
          作为 ``{rel_path: content}`` dict，直接 backend.write。
    """
    name = sanitize_skill_name(_get(package, "package_id", None) or _get(package, "name", None))
    skill_dir = f"{skills_root.rstrip('/')}/{name}"

    written: list[str] = []

    skill_md_path = f"{skill_dir}/SKILL.md"
    backend.write(skill_md_path, render_skill_md(package))
    written.append(skill_md_path)

    # 分支 1：流式路径（整个 extracted/）
    extracted_root = _get(package, "extracted_root", None)
    if isinstance(extracted_root, Path) and extracted_root.is_dir():
        for file in sorted(extracted_root.rglob("*")):
            if not file.is_file():
                continue
            try:
                rel = file.relative_to(extracted_root).as_posix()
            except ValueError:
                continue
            if rel in _SKIP_ROOT_FILES:
                continue
            target = _safe_join(skill_dir, rel)
            if target is None:
                continue
            if _write_extracted_file(backend, target, file, name, rel):
                written.append(target)
        return written

    # 分支 2：dict 路径（后向兼容）
    for asset_dir in ASSET_DIRS:
        files = _get(package, asset_dir, None)
        if not isinstance(files, dict):
            continue
        base = f"{skill_dir}/{asset_dir}"
        for rel_path, content in files.items():
            target = _safe_join(base, rel_path)
            if target is None:
                continue
            backend.write(target, content if isinstance(content, str) else str(content))
            written.append(target)

    return written
