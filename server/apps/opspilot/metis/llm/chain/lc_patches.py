"""LangChain-OpenAI monkey patches (relocated from node.py).

DeepSeek/Qwen thinking mode fix:

Problem: Models like DeepSeek and Qwen return a ``reasoning_content`` field in
their API responses. In multi-turn conversations (e.g. ReAct tool-calling
loops), this field MUST be passed back with the assistant message. However
langchain-openai's deserialization (``_convert_dict_to_message``) discards it,
so on the next turn the field is missing and the model returns HTTP 400:
  "The reasoning_content in the thinking mode must be passed back to the API."

Fix: We monkey-patch BOTH directions:
  1. Response -> AIMessage: preserve reasoning_content in additional_kwargs
  2. AIMessage -> Request dict: inject reasoning_content back into the payload

NOTE: importing this module applies the patches as an import side effect, which
preserves the original behavior of importing ``node`` (which patched on import).
"""

import langchain_openai.chat_models.base as _lc_openai_base
import openai
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_openai.chat_models.base import BaseChatOpenAI as _BaseChatOpenAI
from langchain_openai.chat_models.base import _convert_delta_to_message_chunk as _original_convert_delta_to_message_chunk
from langchain_openai.chat_models.base import _convert_dict_to_message as _original_convert_dict_to_message
from langchain_openai.chat_models.base import _convert_message_to_dict as _original_convert_message_to_dict

# --- Patch 1: Response deserialization (preserve reasoning_content) ----------
#
# Different providers use different field names for thinking/reasoning content:
#   - DeepSeek: "reasoning_content"
#   - Qwen: "reasoning"
# We normalize to "reasoning_content" in additional_kwargs for internal use.
_REASONING_FIELD_NAMES = ("reasoning_content", "reasoning")


def _patched_convert_dict_to_message(_dict, *args, **kwargs):
    """Preserve reasoning_content from provider response into AIMessage.additional_kwargs."""
    message = _original_convert_dict_to_message(_dict, *args, **kwargs)
    if isinstance(message, AIMessage):
        for field_name in _REASONING_FIELD_NAMES:
            if _dict.get(field_name):
                message.additional_kwargs["reasoning_content"] = _dict[field_name]
                break
    return message


_lc_openai_base._convert_dict_to_message = _patched_convert_dict_to_message


# --- Patch 3: _create_chat_result - capture reasoning_content from raw response ----

_original_create_chat_result = _BaseChatOpenAI._create_chat_result


def _patched_create_chat_result(self, response, generation_info=None):
    """Intercept _create_chat_result to extract reasoning_content from the raw response object."""
    # If response is an openai BaseModel, try to get reasoning content from the raw object
    reasoning_contents = {}
    if isinstance(response, openai.BaseModel) and hasattr(response, "choices"):
        for i, choice in enumerate(response.choices):
            msg = getattr(choice, "message", None)
            if msg is not None:
                rc = None
                for field_name in _REASONING_FIELD_NAMES:
                    rc = getattr(msg, field_name, None)
                    if rc:
                        reasoning_contents[i] = rc
                        break
                if not rc:
                    extras = getattr(msg, "model_extra", {}) or {}
                    for field_name in _REASONING_FIELD_NAMES:
                        if extras.get(field_name):
                            reasoning_contents[i] = extras[field_name]
                            break

    result = _original_create_chat_result(self, response, generation_info)

    # Inject reasoning_content into the AIMessage if we found it from raw response
    if reasoning_contents:
        for i, rc in reasoning_contents.items():
            if i < len(result.generations):
                gen_msg = result.generations[i].message
                if isinstance(gen_msg, AIMessage) and "reasoning_content" not in gen_msg.additional_kwargs:
                    gen_msg.additional_kwargs["reasoning_content"] = rc

    return result


_BaseChatOpenAI._create_chat_result = _patched_create_chat_result


# --- Patch 4: _convert_delta_to_message_chunk - preserve reasoning_content in streaming ---


def _patched_convert_delta_to_message_chunk(_dict, default_class, *args, **kwargs):
    """Preserve reasoning_content from streaming delta chunks."""
    chunk = _original_convert_delta_to_message_chunk(_dict, default_class, *args, **kwargs)
    if isinstance(chunk, AIMessageChunk):
        for field_name in _REASONING_FIELD_NAMES:
            if _dict.get(field_name):
                chunk.additional_kwargs["reasoning_content"] = _dict[field_name]
                break
    return chunk


_lc_openai_base._convert_delta_to_message_chunk = _patched_convert_delta_to_message_chunk


# --- Patch 2: Request serialization (inject reasoning_content back) ----------


def _patched_convert_message_to_dict(message, *args, **kwargs):
    """Inject reasoning_content from AIMessage.additional_kwargs into the API request payload."""
    result = _original_convert_message_to_dict(message, *args, **kwargs)
    if isinstance(message, AIMessage) and result.get("role") == "assistant" and "reasoning_content" in message.additional_kwargs:
        result["reasoning_content"] = message.additional_kwargs["reasoning_content"]
    return result


_lc_openai_base._convert_message_to_dict = _patched_convert_message_to_dict
