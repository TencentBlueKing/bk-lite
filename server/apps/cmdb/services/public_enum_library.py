# -- coding: utf-8 --
# @File: public_enum_library.py
# @Time: 2026/3/9
# @Author: windyzhao
import json
import time
from typing import Any

from django.db import transaction
from nanoid import generate

from apps.cmdb.constants.constants import MODEL
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.public_enum_library import PublicEnumLibrary
from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


PUBLIC_ENUM_LIBRARY_MANAGER: Any = getattr(PublicEnumLibrary, "objects")


def _generate_library_id() -> str:
    return f"lib_{generate(size=12)}"


def _validate_options(options: list[dict]) -> None:
    if not isinstance(options, list):
        raise BaseAppException("options 必须是数组")
    seen_ids = set()
    for idx, opt in enumerate(options):
        if not isinstance(opt, dict):
            raise BaseAppException(f"options[{idx}] 必须是对象")
        opt_id = opt.get("id")
        opt_name = opt.get("name")
        if not opt_id or not isinstance(opt_id, str):
            raise BaseAppException(f"options[{idx}].id 必须是非空字符串")
        if not opt_name or not isinstance(opt_name, str):
            raise BaseAppException(f"options[{idx}].name 必须是非空字符串")
        if opt_id in seen_ids:
            raise BaseAppException(f"options 中存在重复的 id: {opt_id}")
        seen_ids.add(opt_id)


def create_library(payload: dict, operator: str) -> dict:
    name = payload.get("name", "").strip()
    if not name:
        raise BaseAppException("公共选项库名称不能为空")

    team = payload.get("team", [])
    if not isinstance(team, list):
        raise BaseAppException("team 必须是数组")

    options = payload.get("options", [])
    _validate_options(options)

    library_id = _generate_library_id()

    library = PUBLIC_ENUM_LIBRARY_MANAGER.create(
        library_id=library_id,
        name=name,
        team=team,
        options=options,
        created_by=operator,
        updated_by=operator,
    )

    logger.info(
        f"[PublicEnumLibrary] created library_id={library_id}, name={name}, operator={operator}"
    )

    return {
        "library_id": library.library_id,
        "name": library.name,
        "team": library.team,
        "options": library.options,
        "created_at": library.created_at.isoformat() if library.created_at else None,
        "updated_at": library.updated_at.isoformat() if library.updated_at else None,
        "created_by": library.created_by,
        "updated_by": library.updated_by,
    }


def update_library(library_id: str, payload: dict, operator: str) -> dict:
    library = PUBLIC_ENUM_LIBRARY_MANAGER.filter(library_id=library_id).first()
    if not library:
        raise BaseAppException("公共选项库不存在")

    update_fields = ["updated_at", "updated_by"]
    library.updated_by = operator

    if "name" in payload:
        name = payload["name"].strip() if payload["name"] else ""
        if not name:
            raise BaseAppException("公共选项库名称不能为空")
        library.name = name
        update_fields.append("name")

    if "team" in payload:
        team = payload["team"]
        if not isinstance(team, list):
            raise BaseAppException("team 必须是数组")
        library.team = team
        update_fields.append("team")

    if "options" in payload:
        options = payload["options"]
        _validate_options(options)
        library.options = options
        update_fields.append("options")

    library.save(update_fields=update_fields)

    logger.info(
        f"[PublicEnumLibrary] updated library_id={library_id}, fields={update_fields}, operator={operator}"
    )

    if "options" in payload:
        enqueue_library_snapshot_refresh(
            library_id, trigger="update", operator=operator
        )

    return {
        "library_id": library.library_id,
        "name": library.name,
        "team": library.team,
        "options": library.options,
        "created_at": library.created_at.isoformat() if library.created_at else None,
        "updated_at": library.updated_at.isoformat() if library.updated_at else None,
        "created_by": library.created_by,
        "updated_by": library.updated_by,
    }


def delete_library(library_id: str, operator: str) -> None:
    library = PUBLIC_ENUM_LIBRARY_MANAGER.filter(library_id=library_id).first()
    if not library:
        raise BaseAppException("公共选项库不存在")

    start_time = time.time()
    references = find_library_references(library_id)
    query_cost_ms = int((time.time() - start_time) * 1000)

    logger.info(
        f"[PublicEnumLibrary] delete_library library_id={library_id}, operator={operator}, "
        f"blocked={len(references) > 0}, reference_count={len(references)}, query_cost_ms={query_cost_ms}"
    )

    if references:
        ref_details = ", ".join(
            f"{ref['model_name']}({ref['model_id']}).{ref['attr_name']}({ref['attr_id']})"
            for ref in references
        )
        raise BaseAppException(
            f"该公共选项库正在被以下属性引用，无法删除: {ref_details}",
            data={"references": references},
        )

    library.delete()
    logger.info(
        f"[PublicEnumLibrary] deleted library_id={library_id}, operator={operator}"
    )


def find_library_references(library_id: str) -> list[dict]:
    start_time = time.time()
    references = []

    with GraphClient() as client:
        models, _ = client.query_entity(MODEL, [])

    for model in models:
        model_id = model.get("model_id", "")
        model_name = model.get("model_name", "")
        attrs = ModelManage.parse_attrs(model.get("attrs", "[]"))

        for attr in attrs:
            if attr.get("attr_type") != "enum":
                continue
            if attr.get("enum_rule_type") != "public_library":
                continue
            if attr.get("public_library_id") != library_id:
                continue

            references.append(
                {
                    "model_id": model_id,
                    "model_name": model_name,
                    "attr_id": attr.get("attr_id", ""),
                    "attr_name": attr.get("attr_name", ""),
                }
            )

    query_cost_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"[PublicEnumLibrary] find_library_references library_id={library_id}, "
        f"query_cost_ms={query_cost_ms}, references_count={len(references)}"
    )

    return references


def enqueue_library_snapshot_refresh(
    library_id: str, trigger: str, operator: str
) -> str:
    from apps.cmdb.tasks.celery_tasks import sync_public_enum_library_snapshots_task

    task = sync_public_enum_library_snapshots_task.delay(library_id, trigger, operator)
    logger.info(
        f"[PublicEnumLibrary] enqueue_library_snapshot_refresh library_id={library_id}, "
        f"trigger={trigger}, operator={operator}, task_id={task.id}"
    )
    return task.id


def get_library_or_raise(library_id: str) -> PublicEnumLibrary:
    library = PUBLIC_ENUM_LIBRARY_MANAGER.filter(library_id=library_id).first()
    if not library:
        raise BaseAppException("公共选项库不存在")
    return library


def list_libraries(team: list | None = None) -> list[dict]:
    queryset = PUBLIC_ENUM_LIBRARY_MANAGER.all().order_by("-created_at")

    libraries = []
    for lib in queryset:
        editable = True
        if team is not None:
            lib_team_set = set(str(t) for t in lib.team)
            user_team_set = set(str(t) for t in team)
            editable = bool(lib_team_set & user_team_set) if lib_team_set else True

        libraries.append(
            {
                "library_id": lib.library_id,
                "name": lib.name,
                "team": lib.team,
                "options": lib.options,
                "editable": editable,
                "created_at": lib.created_at.isoformat() if lib.created_at else None,
                "updated_at": lib.updated_at.isoformat() if lib.updated_at else None,
                "created_by": lib.created_by,
                "updated_by": lib.updated_by,
            }
        )

    return libraries


def sync_library_snapshots(
    library_id: str, trigger: str, operator: str | None = None
) -> dict:
    logger.info(
        f"[SyncPublicEnumSnapshots] started library_id={library_id}, "
        f"trigger={trigger}, operator={operator}"
    )

    library = PUBLIC_ENUM_LIBRARY_MANAGER.filter(library_id=library_id).first()
    if not library:
        logger.warning(
            f"[SyncPublicEnumSnapshots] library not found library_id={library_id}"
        )
        return {
            "result": False,
            "message": "library not found",
            "library_id": library_id,
        }

    new_options = library.options
    affected_models = set()
    affected_attrs = 0
    failed_items = []

    with GraphClient() as client:
        models = client.search_entity(MODEL, [])

        for model in models:
            model_id = model.get("model_id", "")
            model_db_id = model.get("_id")
            attrs = ModelManage.parse_attrs(model.get("attrs", "[]"))
            attrs_changed = False

            for attr in attrs:
                if attr.get("attr_type") != "enum":
                    continue
                if attr.get("enum_rule_type") != "public_library":
                    continue
                if attr.get("public_library_id") != library_id:
                    continue

                attr["option"] = new_options
                attrs_changed = True
                affected_attrs += 1

            if attrs_changed:
                try:
                    client.set_entity_properties(
                        MODEL,
                        [model_db_id],
                        {"attrs": json.dumps(attrs, ensure_ascii=False)},
                        {},
                        [],
                        False,
                    )
                    affected_models.add(model_id)
                except Exception as e:
                    logger.error(
                        f"[SyncPublicEnumSnapshots] failed to update model={model_id}, error={e}"
                    )
                    failed_items.append({"model_id": model_id, "error": str(e)})

    logger.info(
        f"[SyncPublicEnumSnapshots] completed library_id={library_id}, "
        f"affected_models={len(affected_models)}, affected_attrs={affected_attrs}, "
        f"failed_count={len(failed_items)}"
    )

    return {
        "result": True,
        "library_id": library_id,
        "affected_models": len(affected_models),
        "affected_attrs": affected_attrs,
        "failed_count": len(failed_items),
        "failed_items": failed_items,
    }
