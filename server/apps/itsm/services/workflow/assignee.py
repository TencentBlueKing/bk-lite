from typing import Any


class AssigneeBlocked(Exception):
    pass


class AssigneeResolver:
    def __init__(
        self,
        groups: dict[int, dict[str, Any]] | None = None,
        org_users: dict[str, list[str]] | None = None,
        pending_counts: dict[str, int] | None = None,
    ):
        self.groups = groups or {}
        self.org_users = org_users or {}
        self.pending_counts = pending_counts or {}
        self._round = 0

    def resolve(self, node: dict[str, Any], ticket_ctx: dict[str, Any]) -> list[str]:
        source = node.get("assignee") or {}
        kind = source.get("source")
        value = source.get("value")
        people = self._from_source(kind, value, ticket_ctx)
        if not people:
            return self._fallback(node)
        balance = (node.get("multi") or {}).get("balance")
        if balance == "round_robin":
            chosen = people[self._round % len(people)]
            self._round += 1
            return [chosen]
        if balance == "least_pending":
            return [min(people, key=lambda user: self.pending_counts.get(user, 0))]
        return people

    def _from_source(self, kind: str | None, value: Any, ticket_ctx: dict[str, Any]) -> list[str]:
        if kind in {"user", "users"}:
            return list(value or [])
        if kind == "handler_group":
            group = self.groups.get(int(value), {})
            return list(group.get("members") or [])
        if kind in {"org", "group"}:
            return list(self.org_users.get(str(value), []))
        if kind == "variable":
            return self._variable(str(value), ticket_ctx)
        return []

    def _variable(self, name: str, ticket_ctx: dict[str, Any]) -> list[str]:
        if name == "initiator":
            return [ticket_ctx["initiator"]] if ticket_ctx.get("initiator") else []
        if name == "initiator_leader":
            return list(ticket_ctx.get("initiator_leader") or [])
        if name.startswith("form."):
            raw = (ticket_ctx.get("form") or {}).get(name.split(".", 1)[1])
            return [raw] if isinstance(raw, str) and raw else list(raw or [])
        if name.startswith("node."):
            return list((ticket_ctx.get("node_assignees") or {}).get(name.split(".", 1)[1]) or [])
        return []

    def _fallback(self, node: dict[str, Any]) -> list[str]:
        strategy = node.get("fallback")
        if strategy in (None, "", "block"):
            raise AssigneeBlocked(node.get("id") or "")
        if strategy == "skip":
            return []
        return [str(strategy)]
