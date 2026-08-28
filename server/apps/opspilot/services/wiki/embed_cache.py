"""Memoized embedding calls for Wiki hybrid retrieval."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Callable, List, Optional

from django.core.cache import cache

from apps.opspilot.services.wiki.embedding_service import embed_texts

_DEFAULT_TTL = int(os.getenv("WIKI_EMBED_CACHE_TTL", "600"))


def _cache_disabled() -> bool:
    return os.getenv("WIKI_EMBED_CACHE_DISABLE", "0") == "1"


def _provider_scope_key(embed_provider) -> str:
    provider_id = getattr(embed_provider, "id", None) or "none"
    updated_at = getattr(embed_provider, "updated_at", None)
    stamp = updated_at.isoformat() if updated_at is not None else "na"
    return f"{provider_id}:{stamp}"


def _text_cache_key(scope_key: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"wiki:embed:v1:{scope_key}:{digest}"


def embed_texts_cached(
    texts: List[str],
    embed_provider,
    *,
    embed_fn: Optional[Callable[[List[str], object], List[List[float]]]] = None,
    ttl: Optional[int] = None,
) -> List[List[float]]:
    if not texts:
        return []
    if _cache_disabled():
        fn = embed_fn or (lambda batch, provider: embed_texts(batch, provider))
        return fn(texts, embed_provider)

    scope_key = _provider_scope_key(embed_provider)
    effective_ttl = _DEFAULT_TTL if ttl is None else ttl
    fn = embed_fn or (lambda batch, provider: embed_texts(batch, provider))

    results: List[Optional[List[float]]] = [None] * len(texts)
    missing_texts: List[str] = []
    missing_indexes: List[int] = []

    for index, text in enumerate(texts):
        cached = cache.get(_text_cache_key(scope_key, text))
        if isinstance(cached, list) and cached:
            results[index] = cached
        else:
            missing_indexes.append(index)
            missing_texts.append(text)

    if missing_texts:
        fresh_vectors = fn(missing_texts, embed_provider)
        for idx, vector in zip(missing_indexes, fresh_vectors or []):
            results[idx] = vector
            if vector:
                cache.set(_text_cache_key(scope_key, texts[idx]), vector, timeout=effective_ttl)

    return [vector or [] for vector in results]
