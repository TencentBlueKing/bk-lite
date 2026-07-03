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
