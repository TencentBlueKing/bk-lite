import json
import os
from pathlib import Path

from apps.core.logger import node_logger as logger


def load_definition_records(community_dir: str, enterprise_dir: str | None = None) -> list[dict]:
    records = {}

    for file_path, source in _iter_definition_files(community_dir, enterprise_dir):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = json.load(file)
        except Exception as error:
            logger.error(f"Failed to load definition file {file_path}: {error}")
            continue

        if not isinstance(content, list):
            logger.error(f"Definition file {file_path} must be a JSON array")
            continue

        for item in content:
            if not isinstance(item, dict):
                logger.error(f"Definition item in {file_path} must be a JSON object")
                continue
            records[item["id"]] = {**item, "_definition_source": source}

    return list(records.values())


def _iter_definition_files(community_dir: str, enterprise_dir: str | None = None):
    for file_path in _list_json_files(community_dir):
        yield file_path, "community"

    if enterprise_dir and os.path.isdir(enterprise_dir):
        for file_path in _list_json_files(enterprise_dir):
            yield file_path, "enterprise"


def _list_json_files(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []

    return sorted(
        str(Path(directory) / file_name)
        for file_name in os.listdir(directory)
        if file_name.endswith(".json") and os.path.isfile(Path(directory) / file_name)
    )
