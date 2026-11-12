from rest_framework import serializers

from apps.itsm.models import TicketTask


class TicketTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketTask
        fields = ["id", "node_id", "node_name", "assignee", "status"]


class TicketListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sn = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    creator = serializers.CharField()
    tasks = TicketTaskSerializer(many=True)
    sla_target = serializers.CharField()
    sla_due_at = serializers.CharField()
    sla_breached = serializers.BooleanField()

    @classmethod
    def from_ticket(cls, ticket):
        pending = [task for task in ticket.tasks.all() if task.status in {TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED}]
        open_sla = next((record for record in ticket.sla_records.all() if not record.finished_at), None)
        return {
            "id": ticket.id,
            "sn": ticket.sn,
            "title": ticket.title,
            "status": ticket.status.key if ticket.status_id else "",
            "creator": ticket.creator,
            "tasks": pending,
            "sla_target": open_sla.target if open_sla else "",
            "sla_due_at": open_sla.due_at.isoformat() if open_sla else "",
            "sla_breached": bool(open_sla.breached) if open_sla else False,
        }
