"""Parse the per-turn unattended command before composing model prompts."""

import re

_AUTO_COMMAND = re.compile(r"^\s*/auto(?:\s+|$)", re.IGNORECASE)


def parse_auto_command(message):
    if isinstance(message, list):
        texts = [item.get("message", item.get("text", "")) for item in message if isinstance(item, dict) and item.get("type") != "image_url"]
        matched, _ = parse_auto_command(texts[-1] if texts else "")
        return matched, message
    if not isinstance(message, str):
        return False, message
    match = _AUTO_COMMAND.match(message)
    if not match:
        return False, message
    return True, message[match.end() :].strip()


def normalize_auto_request(message, history, *, entry_type="", explicit=False):
    original = message
    matched, message = parse_auto_command(message)
    if matched and history and history[-1].get("event") == "user" and history[-1].get("message") == original:
        history[-1]["message"] = message
    return message, matched or explicit is True or entry_type in {"celery", "nats", "restful"}


def set_unattended_flag(config, unattended):
    config.pop("unattended", None)
    if unattended:
        config["unattended"] = True
