"""把一篇记忆正文拆成可按键更新的卡片，供写入时只改命中的那一类。"""

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"(?m)^###[ \t]+(.+?)\s*$")
_REASON_RE = re.compile(r"(?im)^[ \t]*-[ \t]*reason[ \t]*:[ \t]*(.+?)\s*$")
_ROOT_CAUSE_RE = re.compile(r"(?im)^[ \t]*-[ \t]*root_cause_id[ \t]*:[ \t]*(.+?)\s*$")
_RC_ID_RE = re.compile(r"\bRC-[A-Z0-9]+-\d+\b")
_SUMMARY_LIMIT = 120
_CLASSIFY_NEW_CONTENT_LIMIT = 4000


@dataclass(frozen=True)
class MemoryCard:
    index: int
    heading: str
    body: str
    start: int
    end: int
    keys: frozenset
    summary: str


def normalize_memory_key(value: str) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def extract_card_keys(text: str) -> frozenset:
    keys = set()
    for match in _HEADING_RE.finditer(text or ""):
        heading = match.group(1).strip()
        if heading:
            keys.add(heading)
    for match in _REASON_RE.finditer(text or ""):
        reason = match.group(1).strip()
        if reason:
            keys.add(reason)
    for match in _ROOT_CAUSE_RE.finditer(text or ""):
        root_cause_id = match.group(1).strip()
        if root_cause_id:
            keys.add(root_cause_id)
    for match in _RC_ID_RE.finditer(text or ""):
        keys.add(match.group(0))
    return frozenset(key for key in keys if key)


def parse_memory_cards(content: str) -> list:
    text = content or ""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return []

    cards = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end]
        heading = match.group(1).strip()
        cards.append(
            MemoryCard(
                index=index,
                heading=heading,
                body=body,
                start=start,
                end=end,
                keys=extract_card_keys(body),
                summary=_card_summary(body),
            )
        )
    return cards


def split_incoming_units(content: str) -> list:
    text = (content or "").strip()
    if not text:
        return []
    cards = parse_memory_cards(text)
    if cards:
        return [card.body.strip() for card in cards]
    return [text]


def match_card_by_keys(cards: list, new_keys) -> MemoryCard | None:
    wanted = {normalize_memory_key(key) for key in (new_keys or []) if key}
    wanted.discard("")
    if not wanted or not cards:
        return None

    hits = []
    for card in cards:
        card_keys = {normalize_memory_key(key) for key in card.keys}
        if card_keys & wanted:
            hits.append(card)
    if not hits:
        return None
    for card in hits:
        if normalize_memory_key(card.heading) in wanted:
            return card
    return hits[0]


def render_card_catalog(cards: list) -> str:
    lines = []
    for card in cards:
        keys = "、".join(sorted(card.keys)) or card.heading
        lines.append(f"[{card.index}] 标题={card.heading} 检索键={keys} 摘要={card.summary}")
    return "\n".join(lines)


def truncate_classify_content(content: str, limit: int = _CLASSIFY_NEW_CONTENT_LIMIT) -> str:
    text = content or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(已截断)"


def replace_card(content: str, card: MemoryCard, new_body: str) -> str:
    replacement = (new_body or "").strip()
    if not replacement:
        replacement = card.body.strip()
    if not replacement.lstrip().startswith("###"):
        replacement = f"### {card.heading}\n{replacement}"
    prefix = (content or "")[: card.start].rstrip()
    suffix = (content or "")[card.end :].lstrip()
    parts = []
    if prefix:
        parts.append(prefix)
    parts.append(replacement)
    if suffix:
        parts.append(suffix)
    return "\n\n".join(parts)


def append_card(content: str, new_body: str) -> str:
    addition = (new_body or "").strip()
    if not addition:
        return content or ""
    current = (content or "").rstrip()
    if not current:
        return addition
    return f"{current}\n\n{addition}"


def coerce_updated_card(raw: str, heading: str) -> str:
    text = (raw or "").strip()
    cards = parse_memory_cards(text)
    if not cards:
        if text.lstrip().startswith("###"):
            return text
        return f"### {heading}\n{text}" if text else f"### {heading}"
    wanted = normalize_memory_key(heading)
    for card in cards:
        if normalize_memory_key(card.heading) == wanted:
            return card.body.strip()
    return cards[0].body.strip()


def resolve_catalog_match(cards: list, payload: dict) -> MemoryCard | None:
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip().casefold()
    if action in {"create", "new"}:
        return None
    if action and action not in {"update", "match"}:
        return None

    if "index" in payload and payload.get("index") is not None:
        try:
            index = int(payload["index"])
        except (TypeError, ValueError):
            return None
        for card in cards:
            if card.index == index:
                return card
        return None

    heading = str(payload.get("heading") or payload.get("title") or "").strip()
    if not heading:
        return None
    wanted = normalize_memory_key(heading)
    for card in cards:
        if normalize_memory_key(card.heading) == wanted:
            return card
    return None


def _card_summary(body: str) -> str:
    lines = []
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("###"):
            continue
        lines.append(stripped)
        if len(" ".join(lines)) >= _SUMMARY_LIMIT:
            break
    summary = " ".join(lines)
    if len(summary) <= _SUMMARY_LIMIT:
        return summary
    return summary[:_SUMMARY_LIMIT].rstrip() + "…"
