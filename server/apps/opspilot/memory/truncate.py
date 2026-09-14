"""截断过长记忆正文，避免撑爆对话上下文。"""

MEMORY_CONTEXT_MAX_CHARS = 8000


def truncate_memory_context(memory_context: str, max_chars: int = MEMORY_CONTEXT_MAX_CHARS) -> str:
    """按记忆条目截断过长内容。

    Args:
        memory_context: 记忆内容
        max_chars: 最大字符数（默认 8000，约 2000-4000 tokens）

    Returns:
        截断后的记忆内容
    """
    if not memory_context or len(memory_context) <= max_chars:
        return memory_context

    memories = memory_context.split("\n\n## ")
    if len(memories) <= 1:
        return memory_context[:max_chars] + "\n\n...(记忆内容过长，已截断)"

    if memories[0].startswith("## "):
        memories[0] = memories[0][3:]

    result = []
    current_length = 0
    for i, mem in enumerate(memories):
        mem_with_prefix = f"## {mem}"
        if current_length + len(mem_with_prefix) + 4 > max_chars:
            if result:
                result.append(f"\n\n...(还有 {len(memories) - i} 条记忆未显示)")
            break
        if result:
            result.append("\n\n")
        result.append(mem_with_prefix)
        current_length += len(mem_with_prefix) + 4

    return "".join(result)
