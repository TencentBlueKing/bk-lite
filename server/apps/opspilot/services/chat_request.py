"""Typed normalization of the chat request kwargs dict.

F030: ``ChatService.chat`` / ``ChatService.invoke_chat`` historically accepted an
untyped ``Dict[str, Any]`` and read ~20 keys via a mix of ``kwargs[...]`` and
``kwargs.get(...)``. A missing key surfaced as a ``KeyError`` deep in the call
stack.

``ChatRequest`` parses the incoming kwargs dict ONCE into a typed view. It only
covers the keys that ``chat()`` / ``invoke_chat()`` read directly in their own
bodies; the same kwargs dict is still forwarded unchanged to the downstream
helpers (``format_chat_server_kwargs`` / ``rag_service`` / ``history_service``),
so external behavior is preserved.

Unknown keys are tolerated (ignored). Keys that previously raised ``KeyError``
when absent remain required and are validated explicitly with a clear message.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ChatRequestError(KeyError):
    """Raised when a previously-required kwargs key is missing.

    Subclasses ``KeyError`` so existing ``except KeyError`` handlers (and the
    historical KeyError contract for missing required keys) keep working, while
    surfacing a clearer message.
    """


@dataclass
class ChatRequest:
    """Typed view over the chat kwargs read by ``chat()`` / ``invoke_chat()``."""

    # Required keys (absence previously raised KeyError).
    llm_model: Any

    # Optional keys with their documented defaults.
    # NOTE: only ``chat()`` reads enable_rag_knowledge_source; ``invoke_chat()``
    # never did, so it must NOT be required at the shared parse boundary.
    enable_rag_knowledge_source: bool = False
    show_think: bool = True
    skill_type: Optional[Any] = None
    group: Any = 0

    # Captured for completeness / future typed access; tolerated when absent.
    tools: List[Any] = field(default_factory=list)
    attachment_id: Optional[Any] = None
    node_id: Optional[Any] = None
    trigger_type: Optional[Any] = None

    @classmethod
    def from_kwargs(cls, kwargs: Dict[str, Any]) -> "ChatRequest":
        """Parse ``kwargs`` into a ``ChatRequest``, tolerating unknown keys.

        Required keys are validated explicitly so a missing one yields a clear
        error (still a ``KeyError`` subclass to match prior behavior) instead of
        a bare ``KeyError`` raised deep in the stack.
        """
        try:
            llm_model = kwargs["llm_model"]
        except KeyError:
            raise ChatRequestError("Missing required chat kwarg: 'llm_model'")

        return cls(
            llm_model=llm_model,
            enable_rag_knowledge_source=kwargs.get("enable_rag_knowledge_source", False),
            show_think=kwargs.get("show_think", True),
            skill_type=kwargs.get("skill_type"),
            group=kwargs.get("group", 0),
            tools=kwargs.get("tools", []) or [],
            attachment_id=kwargs.get("attachment_id"),
            node_id=kwargs.get("node_id"),
            trigger_type=kwargs.get("trigger_type"),
        )
