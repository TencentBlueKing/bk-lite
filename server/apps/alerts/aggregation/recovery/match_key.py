from typing import Optional, Tuple

from apps.alerts.models.models import Event


def build_recovery_match_key(event: Event) -> Optional[Tuple[int, str, str, tuple]]:
    """恢复事件主关联键；来源、推送分区和组织均不得被 external_id 放大。"""
    external_id = str(event.external_id or "").strip()
    if not external_id or event.source_id is None:
        return None
    team = tuple(sorted(str(team_id) for team_id in (event.team or [])))
    return (
        event.source_id,
        str(event.push_source_id or "default"),
        external_id,
        team,
    )
