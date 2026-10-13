"""构建冲突文案只按 code 与变体翻译，不把其它队列错误改写成「构建仍在运行」。"""

import json

import pytest

from apps.core.utils.loader import LanguageLoader
from apps.opspilot.services.wiki.directory_service import DirectoryServiceError
from apps.opspilot.services.wiki.material_build_queue_service import MaterialBuildQueueError
from apps.opspilot.utils.user_message import (
    BUILD_CONFLICT_CODE,
    BUILD_CONFLICT_RETRY,
    BUILD_CONFLICT_RUNNING,
    BUILD_CONFLICT_WAIT,
    build_conflict_message,
    queue_error_message,
)
from apps.opspilot.viewsets.wiki_page_view import _directory_service_error

pytestmark = pytest.mark.unit

_CONFLICT_KEYS = (
    "error.knowledge_base_build_running",
    "error.knowledge_base_build_running_wait",
    "error.knowledge_base_build_running_retry",
)


def _loaders():
    return (
        LanguageLoader(app="opspilot", default_lang="en"),
        LanguageLoader(app="opspilot", default_lang="zh-Hans"),
    )


def _conflict_copies(loaders):
    return {loader.get(key) for loader in loaders for key in _CONFLICT_KEYS}


def test_non_conflict_queue_errors_are_not_build_running_copy():
    loaders = _loaders()
    en, zh = loaders
    conflict_copies = _conflict_copies(loaders)
    required = MaterialBuildQueueError("material_ids_required", "material_ids 必填", status_code=400)
    missing = MaterialBuildQueueError("knowledge_base_not_found", "知识库不存在", status_code=404)
    oversized = MaterialBuildQueueError("material_ids_too_many", "单次最多排队 200 条资料", status_code=400)
    # 原句带上旧启发式会命中的全角逗号和「重试」，仍然不能变成冲突文案。
    decoy = MaterialBuildQueueError("material_ids_required", "material_ids 必填，请重试", status_code=400)

    for loader in loaders:
        for error in (required, oversized, decoy):
            text = queue_error_message(None, error, loader)
            assert text == error.message
            assert text not in conflict_copies
        missing_text = queue_error_message(None, missing, loader)
        assert missing_text not in conflict_copies
        assert "still running" not in missing_text.lower()
        assert "运行中的构建" not in missing_text

    assert queue_error_message(None, missing, en) == en.get("error.knowledge_base_not_found")
    assert queue_error_message(None, missing, zh) == zh.get("error.knowledge_base_not_found")
    assert queue_error_message(None, required, en) == "material_ids 必填"
    assert "still running" not in queue_error_message(None, required, en).lower()
    assert "运行中的构建" not in queue_error_message(None, required, zh)
    assert "still running" not in queue_error_message(None, oversized, en).lower()


def test_conflict_code_selects_catalog_by_variant_not_chinese_source():
    en, zh = _loaders()
    retry_sentence = "知识库存在运行中的构建任务，请等待完成后再重试"
    wait_sentence = "知识库存在运行中的构建任务，请等待完成后再操作"

    running = MaterialBuildQueueError(
        BUILD_CONFLICT_CODE,
        retry_sentence,
        status_code=409,
        conflict_variant=BUILD_CONFLICT_RUNNING,
    )
    waiting = MaterialBuildQueueError(
        BUILD_CONFLICT_CODE,
        retry_sentence,
        status_code=409,
        conflict_variant=BUILD_CONFLICT_WAIT,
    )
    retrying = MaterialBuildQueueError(
        BUILD_CONFLICT_CODE,
        wait_sentence,
        status_code=409,
        conflict_variant=BUILD_CONFLICT_RETRY,
    )

    assert queue_error_message(None, running, zh) == zh.get("error.knowledge_base_build_running")
    assert queue_error_message(None, waiting, zh) == zh.get("error.knowledge_base_build_running_wait")
    assert queue_error_message(None, retrying, en) == en.get("error.knowledge_base_build_running_retry")
    assert "retrying" in queue_error_message(None, retrying, en).lower()
    assert "重试" in queue_error_message(None, retrying, zh)
    # 原句含「重试」和全角逗号，变体仍决定词条。
    assert queue_error_message(None, running, en) != en.get("error.knowledge_base_build_running_retry")
    assert queue_error_message(None, running, zh) != zh.get("error.knowledge_base_build_running_retry")
    assert queue_error_message(None, waiting, zh) != zh.get("error.knowledge_base_build_running")


def test_build_conflict_message_without_conflict_code_keeps_original():
    en = LanguageLoader(app="opspilot", default_lang="en")
    original = "知识库不存在"
    assert build_conflict_message(None, original, en) == original
    assert build_conflict_message(None, original, en, code="knowledge_base_not_found") == original
    assert build_conflict_message(None, "material_ids 必填", en) == "material_ids 必填"
    translated = build_conflict_message(
        None,
        original,
        en,
        code=BUILD_CONFLICT_CODE,
        variant=BUILD_CONFLICT_WAIT,
    )
    assert translated == en.get("error.knowledge_base_build_running_wait")
    assert "still running" in translated.lower()


def test_directory_service_error_translates_only_conflict_code():
    en = LanguageLoader(app="opspilot", default_lang="en")
    other = DirectoryServiceError("knowledge_base_not_found", "知识库不存在")
    other_body = json.loads(_directory_service_error(other, request=None, loader=en).content)
    assert other_body["code"] == "knowledge_base_not_found"
    assert other_body["message"] == "知识库不存在"
    assert "still running" not in other_body["message"].lower()

    # 原句没有「重试」，旧启发式会选 wait；变体 retry 才应选出 retry 词条。
    conflict = DirectoryServiceError(
        BUILD_CONFLICT_CODE,
        "知识库存在运行中的构建任务，请等待完成后再操作",
        status_code=409,
        retryable=True,
        conflict_variant=BUILD_CONFLICT_RETRY,
    )
    body = json.loads(_directory_service_error(conflict, request=None, loader=en).content)
    assert body["code"] == BUILD_CONFLICT_CODE
    assert body["message"] == en.get("error.knowledge_base_build_running_retry")
    assert "retrying" in body["message"].lower()
