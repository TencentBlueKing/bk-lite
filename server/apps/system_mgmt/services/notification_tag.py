import re

from rest_framework import serializers

from apps.core.models.maintainer_info import maintainer_kwargs
from apps.system_mgmt.models import NotificationTag

_FORBIDDEN = re.compile(r"[: \n\r,]")
_MAX_LENGTH = 64


def parse_tag_tokens(values):
    """把 ["用途:ITSM"] 解析成去重后的 (key, value) 列表。"""
    if not isinstance(values, list):
        raise serializers.ValidationError("tag must be a list")

    pairs = []
    seen = set()
    for raw in values:
        text = str(raw).strip()
        if text.count(":") != 1:
            raise serializers.ValidationError("tag must be key:value")
        key, value = (part.strip() for part in text.split(":", 1))
        if not key or not value or len(key) > _MAX_LENGTH or len(value) > _MAX_LENGTH or _FORBIDDEN.search(key) or _FORBIDDEN.search(value):
            raise serializers.ValidationError("tag must be key:value")
        token = (key, value)
        if token in seen:
            continue
        seen.add(token)
        pairs.append(token)
    return pairs


def assign_channel_tags(channel, pairs, *, actor=None):
    defaults = {}
    username = getattr(actor, "username", None)
    if username:
        defaults = maintainer_kwargs(operator=username, domain=getattr(actor, "domain", None))
    tags = []
    for key, value in pairs:
        tag, _created = NotificationTag.objects.get_or_create(key=key, value=value, defaults=defaults)
        tags.append(tag)
    channel.tags.set(tags)


def channel_tag_tokens(channel):
    tags = sorted(channel.tags.all(), key=lambda tag: tag.id)
    return [f"{tag.key}:{tag.value}" for tag in tags]
