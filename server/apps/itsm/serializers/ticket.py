from rest_framework import serializers

from apps.itsm.models import TicketTask


class TicketTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketTask
        fields = ["id", "node_id", "node_name", "assignee", "status"]


class TicketListSerializer(serializers.BaseSerializer):
    def to_representation(self, ticket):
        from apps.itsm.services.ticket.listing import COLUMNS

        fields = self.context.get("fields")
        wanted = fields if fields is not None else set(COLUMNS)
        result = {"id": ticket.id, "sn": ticket.sn, "title": ticket.title}
        for key in wanted.intersection({"creator", "created_at", "updated_at"}):
            value = getattr(ticket, key)
            result[key] = value.isoformat() if hasattr(value, "isoformat") else value
        if "status" in wanted:
            result["status"] = ticket.status.key if ticket.status_id else ""
        if "priority" in wanted:
            result["priority"] = str(ticket._priority or "")
        if "workflow" in wanted:
            result["workflow"] = ticket.workflow.name
        if wanted.intersection({"node", "assignees"}):
            result["tasks"] = TicketTaskSerializer(ticket.tasks.all(), many=True).data
        if "sla" in wanted:
            sla = next(iter(ticket.sla_records.all()), None)
            result.update(
                sla_target=sla.target if sla else "", sla_due_at=sla.due_at.isoformat() if sla else "", sla_breached=bool(sla and sla.breached)
            )
        return result
