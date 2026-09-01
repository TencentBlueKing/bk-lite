"""OpsPilot runtime optimization PR4: embed cache + skill materialize cache."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


class TestEmbedTextsCached:
    @pytest.fixture(autouse=True)
    def _locmem_cache(self, settings):
        settings.CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        }

    def test_second_call_uses_cache(self, monkeypatch):
        from django.core.cache import cache

        from apps.opspilot.services.wiki import embed_cache

        cache.clear()
        monkeypatch.setenv("WIKI_EMBED_CACHE_DISABLE", "0")
        calls = {"n": 0}

        def _embed(texts, _provider):
            calls["n"] += 1
            return [[float(len(t))] for t in texts]

        provider = MagicMock()
        provider.id = 42
        provider.updated_at = None

        first = embed_cache.embed_texts_cached(["hello"], provider, embed_fn=_embed)
        second = embed_cache.embed_texts_cached(["hello"], provider, embed_fn=_embed)
        assert first == second
        assert calls["n"] == 1

    def test_disable_env_bypasses_cache(self, monkeypatch):
        from django.core.cache import cache

        from apps.opspilot.services.wiki import embed_cache

        cache.clear()
        monkeypatch.setenv("WIKI_EMBED_CACHE_DISABLE", "1")
        calls = {"n": 0}

        def _embed(texts, _provider):
            calls["n"] += 1
            return [[1.0] for _ in texts]

        provider = MagicMock()
        provider.id = 7
        provider.updated_at = None

        embed_cache.embed_texts_cached(["a"], provider, embed_fn=_embed)
        embed_cache.embed_texts_cached(["a"], provider, embed_fn=_embed)
        assert calls["n"] == 2


class TestSkillMaterializeCache:
    def test_cache_key_changes_with_content_hash(self):
        from apps.opspilot.services.skill_package.materialize_cache import build_materialize_cache_key

        pkg_a = MagicMock()
        pkg_a.id = 1
        pkg_a.updated_at = None
        pkg_a.content_hash = "aaa"

        pkg_b = MagicMock()
        pkg_b.id = 1
        pkg_b.updated_at = None
        pkg_b.content_hash = "bbb"

        assert build_materialize_cache_key(pkg_a) != build_materialize_cache_key(pkg_b)

    def test_store_and_read_cached_dir(self, monkeypatch, tmp_path):
        from apps.opspilot.services.skill_package.materialize_cache import (
            build_materialize_cache_key,
            cached_materialize_dir,
            store_materialized_dir,
        )

        cache_root = tmp_path / "cache"
        monkeypatch.setenv("OPSPILOT_SKILL_MATERIALIZE_CACHE", str(cache_root))

        pkg = MagicMock()
        pkg.id = 5
        pkg.content_hash = "hash"
        pkg.updated_at = None

        source = tmp_path / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("# demo", encoding="utf-8")

        stored = store_materialized_dir(pkg, source)
        assert stored is not None
        assert stored.is_dir()
        assert cached_materialize_dir(pkg) == stored
        assert build_materialize_cache_key(pkg) in stored.name

    def test_copy_cached_into_target(self, tmp_path):
        from apps.opspilot.services.skill_package.materialize_cache import copy_cached_into

        cached = tmp_path / "cached"
        cached.mkdir()
        (cached / "SKILL.md").write_text("cached", encoding="utf-8")
        nested = cached / "scripts"
        nested.mkdir()
        (nested / "run.sh").write_text("echo", encoding="utf-8")

        target = tmp_path / "target"
        copy_cached_into(target, cached)
        assert (target / "SKILL.md").read_text(encoding="utf-8") == "cached"
        assert (target / "scripts" / "run.sh").exists()

    def test_cached_materialize_dir_disabled_without_env(self, monkeypatch):
        from apps.opspilot.services.skill_package.materialize_cache import cached_materialize_dir

        monkeypatch.delenv("OPSPILOT_SKILL_MATERIALIZE_CACHE", raising=False)
        assert cached_materialize_dir(MagicMock()) is None

    def test_hydrate_uses_cached_extracted_root(self, monkeypatch, tmp_path):
        from apps.opspilot.services.skill_package import runtime

        cached_dir = tmp_path / "cached"
        cached_dir.mkdir()
        (cached_dir / "SKILL.md").write_text("# skill", encoding="utf-8")

        stored = MagicMock()
        stored.id = 99
        stored.package_id = "demo"
        stored.name = "Demo"
        stored.version = "1"
        stored.description = ""
        stored.category = ""
        stored.required_tools = []
        stored.triggers = []
        stored.skill_markdown = "body"
        stored.storage_path = str(tmp_path / "storage")
        stored.is_enabled = True

        monkeypatch.setenv("OPSPILOT_SKILL_MATERIALIZE_CACHE", str(tmp_path / "cache-root"))
        monkeypatch.setattr(
            runtime,
            "cached_materialize_dir",
            lambda _pkg: cached_dir,
        )
        monkeypatch.setattr(
            runtime,
            "run_with_db_cleanup",
            lambda fn: fn(),
        )
        monkeypatch.setattr(
            "apps.opspilot.models.SkillPackage.objects.filter",
            MagicMock(return_value=MagicMock(__iter__=lambda self: iter([stored]), __len__=lambda self: 1)),
        )

        hydrated = runtime.hydrate_skill_packages([{"id": 99}])
        assert hydrated[0]["extracted_root"] == cached_dir
