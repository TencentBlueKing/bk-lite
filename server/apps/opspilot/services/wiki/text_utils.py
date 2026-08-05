import math

LLM_CHUNK_CHARS = 8000
LLM_CHUNK_OVERLAP = 400


def split_text_for_llm(text, max_chars=LLM_CHUNK_CHARS, overlap_chars=LLM_CHUNK_OVERLAP):
    """Split long markdown/text into stable chunks without dropping the tail."""
    normalized = (text or "").strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    chunks = []
    start = 0
    length = len(normalized)
    while start < length:
        hard_end = min(start + max_chars, length)
        end = hard_end
        if hard_end < length:
            candidates = [
                normalized.rfind("\n\n", start, hard_end),
                normalized.rfind("\n", start, hard_end),
                normalized.rfind("。", start, hard_end),
                normalized.rfind(".", start, hard_end),
            ]
            boundary = max(candidates)
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def split_text_by_estimated_tokens(
    text,
    *,
    max_tokens,
    overlap_chars=LLM_CHUNK_OVERLAP,
):
    """Split complete text into semantic chunks below an estimated token ceiling."""

    from apps.opspilot.services.wiki.wiki_budget_service import estimate_tokens

    normalized = (text or "").strip()
    if not normalized:
        return []
    max_tokens = max(int(max_tokens), 1)
    overlap_chars = max(int(overlap_chars), 0)
    if estimate_tokens(normalized) <= max_tokens:
        return [normalized]

    chunks = []
    start = 0
    length = len(normalized)
    while start < length:
        low = start + 1
        high = length
        best_end = low
        while low <= high:
            middle = (low + high) // 2
            if estimate_tokens(normalized[start:middle]) <= max_tokens:
                best_end = middle
                low = middle + 1
            else:
                high = middle - 1

        end = best_end
        if end < length:
            floor = start + max((end - start) // 2, 1)
            candidates = [
                normalized.rfind("\n\n", floor, end),
                normalized.rfind("\n", floor, end),
                normalized.rfind("。", floor, end),
                normalized.rfind(".", floor, end),
            ]
            boundary = max(candidates)
            if boundary >= floor:
                candidate_end = boundary + 1
                if estimate_tokens(normalized[start:candidate_end]) <= max_tokens:
                    end = candidate_end

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        safe_overlap = min(overlap_chars, max((end - start) // 4, 0))
        start = max(end - safe_overlap, start + 1)
    return chunks


def plan_bounded_map_chunks(
    text,
    *,
    max_chunks=4,
    preferred_chars=LLM_CHUNK_CHARS,
    overlap_chars=LLM_CHUNK_OVERLAP,
):
    """Plan no more than ``max_chunks`` contiguous Map inputs without truncation.

    The general-purpose splitter may produce an extra short tail because of
    overlap and semantic boundaries. A Map budget limits LLM calls, not parser
    segments, so progressively enlarge the Map input size until the complete
    source fits in the bounded number of calls. Token and model-window limits
    remain enforced by the caller before each LLM invocation.
    """

    normalized = (text or "").strip()
    if not normalized:
        return []
    max_chunks = max(int(max_chunks), 1)
    preferred_chars = max(int(preferred_chars), 1)
    overlap_chars = max(min(int(overlap_chars), preferred_chars - 1), 0)

    if len(normalized) <= preferred_chars * max_chunks:
        chunks = split_text_for_llm(
            normalized,
            max_chars=preferred_chars,
            overlap_chars=overlap_chars,
        )
        if len(chunks) <= max_chunks:
            return chunks

    max_chars = max(
        preferred_chars,
        math.ceil((len(normalized) + overlap_chars * (max_chunks - 1)) / max_chunks),
    )
    while True:
        chunks = split_text_for_llm(
            normalized,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        if len(chunks) <= max_chunks:
            return chunks
        if max_chars >= len(normalized):
            return [normalized]
        max_chars = min(
            len(normalized),
            max(max_chars + 1, math.ceil(max_chars * 1.25)),
        )
