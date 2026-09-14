from django_filters import CharFilter, FilterSet

from apps.alerts.models.notification_template import NotificationTemplate


class NotificationTemplateFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains")
    scope = CharFilter(field_name="scope", lookup_expr="exact")

    class Meta:
        model = NotificationTemplate
        fields = ["name", "scope"]
