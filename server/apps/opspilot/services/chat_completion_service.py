"""Shared business logic for OpenAI-compatible chat completion endpoints.

``openai_completions`` (v1/chat/completions) uses this service to parse the JSON
body, resolve the caller IP, detect stream mode, validate the API token, resolve
the target skill + invocation params, enrich params, then dispatch to either the
non-streaming JSON response or the streaming SSE response.

The service intentionally delegates token validation, skill resolution and
chat invocation back through the callables supplied by the view layer. This
keeps the existing patch targets (e.g. ``apps.opspilot.views.validate_openai_token``,
``apps.opspilot.views.get_skill_and_params``, ``apps.opspilot.views.ChatService``)
authoritative and avoids any behavior drift.
"""

from typing import Any, Callable, Optional

from django.http import JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.caller_identity import CallerIdentityError


class ChatCompletionService:
    """Holds the shared token-validation / skill-resolution / stream logic
    used by the OpenAI-compatible chat completion endpoint.

    Callers customize behavior via injected callables:

    * how the caller token is validated (``validate``) and how the resulting
      identity exposes its ``username`` (``get_user_id``);
    * the arguments passed to skill resolution (``resolve_skill``);
    * optional post-resolution hooks (``enrich_params`` / ``post_resolve_hook``).

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

    def _internal_enrich_error_response(self, stream_mode: bool):
        error_message = "Internal server error"
        if stream_mode:
            response = self._generate_stream_error(error_message)
            response.status_code = 500
            return response
        return JsonResponse(
            {"choices": [{"message": {"role": "assistant", "content": error_message}}]},
            status=500,
        )

    def run(
        self,
        request,
        *,
        validate: Callable[[str, dict], tuple[bool, Any]],
        resolve_skill: Callable[[dict, Any], tuple[Any, Optional[dict], Optional[dict]]],
        get_user_id: Callable[[Any], str],
        enrich_params: Optional[Callable[[Any, Any, dict], None]] = None,
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
            enrich_params: Optional server-side callback invoked immediately
                after validation with ``(request, user, server_params)``. The
                fresh server-owned mapping is merged after skill resolution so
                its values override request- or skill-derived params.
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

        server_enriched_params = {}
        if enrich_params is not None:
            try:
                enrich_params(request, user, server_enriched_params)
            except CallerIdentityError as e:
                status_code = e.status_code
                if type(status_code) is int and 400 <= status_code <= 599:
                    if stream_mode:
                        return self._generate_stream_error(str(e))
                    return JsonResponse(
                        {"choices": [{"message": {"role": "assistant", "content": str(e)}}]},
                        status=status_code,
                    )
                logger.exception("Caller identity enrichment returned an invalid status code")
                return self._internal_enrich_error_response(stream_mode)
            except Exception:
                logger.exception("Unexpected chat completion parameter enrichment failure")
                return self._internal_enrich_error_response(stream_mode)

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
        params["enable_suggest"] = skill_obj.enable_suggest
        params["enable_query_rewrite"] = skill_obj.enable_query_rewrite
        params.update(server_enriched_params)
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
