"""Shared business logic for OpenAI-compatible chat completion endpoints.

`openai_completions` (v1/chat/completions) and `lobe_skill_execute`
(lobe_chat/v1/chat/completions) share ~80% of their flow: parse the JSON body,
resolve the caller IP, detect stream mode, validate the API token, resolve the
target skill + invocation params, enrich the params with skill-level toggles,
then dispatch to either the non-streaming JSON response or the streaming SSE
response.

This module extracts that shared flow into ``ChatCompletionService`` so both
views become thin adapters. The request/response/stream behavior is preserved
byte-for-byte; the OpenAI ``{"choices": [...]}`` envelope is untouched.

The service intentionally delegates token validation, skill resolution and
chat invocation back through the callables supplied by the view layer. This
keeps the existing patch targets (e.g. ``apps.opspilot.views.validate_openai_token``,
``apps.opspilot.views.get_skill_and_params``, ``apps.opspilot.views.ChatService``)
authoritative and avoids any behavior drift.
"""

from typing import Any, Callable, Optional

from django.http import JsonResponse


class ChatCompletionService:
    """Holds the shared token-validation / skill-resolution / stream logic
    used by the OpenAI-compatible chat completion endpoints.

    The two endpoints differ only in:

    * how the caller token is validated (``validate_fn``) and how the resulting
      identity exposes its ``username`` (``user_id_getter``);
    * the arguments passed to skill resolution (``skill_resolver``);
    * an optional post-resolution hook (``post_resolve_hook``) that lobe uses to
      persist conversation history and build a ``history_log``.

    Everything else — JSON parsing, stream-mode detection, error envelopes,
    common param enrichment, and dispatch to invoke/stream — is identical and
    lives here.
    """

    def __init__(
        self,
        *,
        parse_json_body: Callable,
        extract_api_token: Callable,
        get_client_ip: Callable,
        generate_stream_error: Callable,
        insert_skill_log: Callable,
        invoke_chat: Callable,
        stream_chat: Callable,
    ) -> None:
        self._parse_json_body = parse_json_body
        self._extract_api_token = extract_api_token
        self._get_client_ip = get_client_ip
        self._generate_stream_error = generate_stream_error
        self._insert_skill_log = insert_skill_log
        self._invoke_chat = invoke_chat
        self._stream_chat = stream_chat

    def run(
        self,
        request,
        *,
        validate: Callable[[str, dict], tuple[bool, Any]],
        resolve_skill: Callable[[dict, Any], tuple[Any, Optional[dict], Optional[dict]]],
        get_user_id: Callable[[Any], str],
        post_resolve_hook: Optional[Callable[[dict, Any, str, Any, dict], Optional[Any]]] = None,
    ):
        """Execute the shared completion flow.

        Args:
            request: Django request.
            validate: Called with ``(extracted_token, parsed_body)``; returns
                ``(is_valid, msg)`` where ``msg`` is the validated identity on
                success, or an OpenAI error envelope on failure.
            resolve_skill: Called with ``(parsed_body, user)``; returns
                ``(skill_obj, params, error)`` like ``get_skill_and_params``.
            get_user_id: Extracts the ``username`` from the validated identity.
            post_resolve_hook: Optional callback invoked after params are enriched.
                Receives ``(params, skill_obj, user_message, user, parsed_body)``
                and may return a ``history_log`` to thread into the chat
                invocation.

        Returns:
            A Django response identical to the legacy view output.
        """
        kwargs, parse_error = self._parse_json_body(request)
        if parse_error:
            return JsonResponse(
                {"choices": [{"message": {"role": "assistant", "content": parse_error}}]},
                status=400,
            )
        current_ip, _ = self._get_client_ip(request)

        stream_mode = kwargs.get("stream", False)
        token = self._extract_api_token(request)

        is_valid, msg = validate(token, kwargs)
        if not is_valid:
            if stream_mode:
                return self._generate_stream_error(msg["choices"][0]["message"]["content"])
            else:
                return JsonResponse(msg)
        user = msg
        try:
            skill_obj, params, error = resolve_skill(kwargs, user)
            if error:
                if skill_obj:
                    user_message = params.get("user_message")
                    self._insert_skill_log(current_ip, skill_obj.id, error, kwargs, False, user_message)
                if stream_mode:
                    return self._generate_stream_error(error["choices"][0]["message"]["content"])
                else:
                    return JsonResponse(error)
        except Exception as e:
            if stream_mode:
                return self._generate_stream_error(str(e))
            else:
                return JsonResponse({"choices": [{"message": {"role": "assistant", "content": str(e)}}]})
        params["user_id"] = get_user_id(user)
        params["enable_km_route"] = skill_obj.enable_km_route
        params["km_llm_model"] = skill_obj.km_llm_model
        params["enable_suggest"] = skill_obj.enable_suggest
        params["enable_query_rewrite"] = skill_obj.enable_query_rewrite
        user_message = params.get("user_message")

        history_log = None
        if post_resolve_hook is not None:
            history_log = post_resolve_hook(params, skill_obj, user_message, user, kwargs)

        if not stream_mode:
            return self._invoke_chat(params, skill_obj, kwargs, current_ip, user_message, history_log)
        return self._stream_chat(
            params,
            skill_obj.name,
            kwargs,
            current_ip,
            user_message,
            history_log=history_log,
        )
