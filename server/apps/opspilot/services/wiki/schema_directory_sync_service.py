"""从 Schema Markdown 解析并同步知识目录树。"""

from __future__ import annotations

import re
from copy import deepcopy

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.wiki.structure_service import UNCLASSIFIED_DIRECTORY_KEY, StructureServiceError, get_structure, save_structure

_PATH_ITEM = re.compile(r"^-\s+`([^`]+)`(.*)$")
_TYPE_ITEM = re.compile(r"^-\s+([^`\n]+?)\s+\(`([^`]+)`")
_INLINE_TYPE = re.compile(r"[（(]`([^`]+)`[)）]")


def parse_schema_markdown(schema_md):
    """Parse directory paths and page types from Schema markdown.

    Path items look like ``- `wiki/operations`：...（`concept`）``.
    Type items look like ``- 实体 (`entity`: ...)``.
    """
    text = str(schema_md or "")
    page_types = []
    seen_types = set()
    paths = []
    seen_paths = set()
    type_dirs = []

    def add_type(value):
        name = str(value or "").strip()
        if not name:
            return ""
        identity = name.casefold()
        if identity not in seen_types:
            seen_types.add(identity)
            page_types.append(name)
        return name

    for raw_line in text.splitlines():
        line = raw_line.strip()
        path_match = _PATH_ITEM.match(line)
        if path_match:
            raw_path = path_match.group(1).replace("\\", "/").strip().strip("/")
            rest = path_match.group(2) or ""
            if not raw_path:
                continue
            parts = tuple(part for part in raw_path.split("/") if part.strip())
            if not parts or parts in seen_paths:
                continue
            seen_paths.add(parts)
            inline = _INLINE_TYPE.search(rest)
            paths.append(
                {
                    "parts": parts,
                    "page_type": add_type(inline.group(1) if inline else ""),
                    "description": rest.lstrip("：:").strip(),
                }
            )
            continue
        type_match = _TYPE_ITEM.match(line)
        if type_match:
            add_type(type_match.group(2))
            display = type_match.group(1).strip()
            if display:
                type_dirs.append(
                    {
                        "parts": (display,),
                        "page_type": add_type(type_match.group(2)),
                        "description": "",
                    }
                )

    if not paths:
        paths = type_dirs
    else:
        paths = _prefix_wiki_root_when_documented(text, paths)
    return {"page_types": page_types, "paths": paths}


_ASCII_FOLDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _prefix_wiki_root_when_documented(text, paths):
    """Hermes 说明常写「第一层为 wiki/」但列表只列 `architecture`。

    若文内出现 wiki/ 且条目都是单层英文目录名，则挂到 wiki 下，避免导入对不齐。
    """
    if not paths:
        return paths
    if any((item["parts"] or ("",))[0].casefold() == "wiki" for item in paths):
        return paths
    if "wiki/" not in text.replace("\\", "/"):
        return paths
    if not all(len(item["parts"]) == 1 and _ASCII_FOLDER.match(item["parts"][0]) for item in paths):
        return paths
    return [{**item, "parts": ("wiki",) + item["parts"]} for item in paths]


def _prefix_nodes(paths):
    nodes = {}
    for item in paths:
        parts = item["parts"]
        for index in range(len(parts)):
            prefix = parts[: index + 1]
            current = nodes.setdefault(
                prefix,
                {
                    "parts": prefix,
                    "name": prefix[-1],
                    "page_type": "",
                    "description": "",
                },
            )
            if prefix == parts:
                if item.get("page_type"):
                    current["page_type"] = item["page_type"]
                if item.get("description"):
                    current["description"] = item["description"]
    return [nodes[key] for key in sorted(nodes, key=lambda value: (len(value), value))]


def apply_schema_markdown_structure(knowledge_base, schema_md, *, operator=""):
    """Replace schema directories with the tree parsed from Schema markdown.

    Returns the save_structure result, or None when markdown has no directories.
    """
    parsed = parse_schema_markdown(schema_md)
    if not parsed["paths"]:
        return None

    current = get_structure(knowledge_base)
    snapshot = current["structure"]
    existing = list(snapshot.get("directories") or [])
    unclassified = next(
        (item for item in existing if item.get("key") == UNCLASSIFIED_DIRECTORY_KEY),
        None,
    )
    if unclassified is None:
        raise StructureServiceError(
            "active_structure_missing",
            "知识库缺少系统待归类目录",
            status_code=409,
        )

    page_types = list(parsed["page_types"] or snapshot.get("page_types") or ["concept"])
    if not page_types:
        page_types = ["concept"]
    type_lookup = {item.casefold(): item for item in page_types}

    nodes = _prefix_nodes(parsed["paths"])
    existing_by_parent_name = {}
    for item in existing:
        if item.get("status") and item.get("status") != "active":
            continue
        parent = item.get("parent")
        parent_id = parent["id"] if parent else None
        existing_by_parent_name[(parent_id, str(item.get("name") or "").casefold())] = item

    payload_dirs = [{"kind": "existing", **deepcopy(unclassified)}]
    anchors = {(): {"id": None}}
    default_owners = set()
    client_index = 0

    for node in nodes:
        parent_parts = node["parts"][:-1]
        parent_anchor = anchors[parent_parts]
        if "client_ref" in parent_anchor:
            hit = None
            parent_ref = {"client_ref": parent_anchor["client_ref"]}
        elif parent_anchor.get("id"):
            parent_ref = {"id": parent_anchor["id"], "key": parent_anchor["key"]}
            hit = existing_by_parent_name.get((parent_anchor["id"], node["name"].casefold()))
        else:
            parent_ref = None
            hit = existing_by_parent_name.get((None, node["name"].casefold()))
        if hit and hit.get("key") == UNCLASSIFIED_DIRECTORY_KEY:
            hit = None
        page_type = type_lookup.get((node["page_type"] or "").casefold(), "")
        allowed = [page_type] if page_type else list(page_types)
        defaults = []
        if page_type and page_type not in default_owners:
            defaults = [page_type]
            default_owners.add(page_type)

        if hit and hit.get("key") != UNCLASSIFIED_DIRECTORY_KEY:
            payload_dirs.append(
                {
                    "kind": "existing",
                    **deepcopy(hit),
                    "name": node["name"],
                    "description": node["description"] or hit.get("description") or "",
                    "order": (len(payload_dirs) + 1) * 10,
                    "rules": {
                        "allowed_page_types": allowed,
                        "default_for_page_types": defaults,
                    },
                    "parent": parent_ref,
                }
            )
            anchors[node["parts"]] = {"id": hit["id"], "key": hit["key"]}
            continue

        client_index += 1
        client_ref = f"schema-md-{client_index}"
        payload_dirs.append(
            {
                "kind": "new",
                "client_ref": client_ref,
                "name": node["name"],
                "description": node["description"] or "",
                "order": (len(payload_dirs) + 1) * 10,
                "rules": {
                    "allowed_page_types": allowed,
                    "default_for_page_types": defaults,
                },
                "parent": parent_ref,
            }
        )
        anchors[node["parts"]] = {"client_ref": client_ref}

    for item in existing:
        origin = item.get("origin")
        if origin == "manual" and item.get("status") == "active":
            if not any(entry.get("kind") == "existing" and entry.get("id") == item.get("id") for entry in payload_dirs):
                payload_dirs.append({"kind": "existing", **deepcopy(item)})

    result = save_structure(
        knowledge_base,
        {
            "structure_version": current["structure_revision"]["version"],
            "base_generation_id": current["active_generation"]["id"],
            "structure": {
                "format_version": 1,
                "page_types": page_types,
                "directories": payload_dirs,
            },
        },
        operator=operator,
    )
    logger.info(
        "wiki_schema_md_structure_applied kb=%s directories=%s",
        knowledge_base.pk,
        len(nodes),
    )
    return result
