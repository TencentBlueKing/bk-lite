from django.urls import path

from apps.itsm.views.api import (
    dictionaries,
    dictionary_items,
    export_dictionaries,
    form_versions,
    forms,
    handler_groups,
    import_dictionaries,
    notify_templates,
    preview_form,
    publish_form,
    publish_workflow,
    workflow_design,
    workflow_types,
    workflow_variables,
    workflows,
)
from apps.itsm.views.health import health
from apps.itsm.views.tickets import operate_ticket, ticket_logs, tickets

urlpatterns = [
    path("api/health/", health, name="itsm-health"),
    path("api/forms/", forms, name="itsm-forms"),
    path("api/forms/<int:form_id>/versions/", form_versions, name="itsm-form-versions"),
    path("api/forms/<int:form_id>/publish/", publish_form, name="itsm-form-publish"),
    path("api/forms/<int:form_id>/preview/", preview_form, name="itsm-form-preview"),
    path("api/dictionaries/", dictionaries, name="itsm-dictionaries"),
    path("api/dictionaries/<int:dictionary_id>/items/", dictionary_items, name="itsm-dictionary-items"),
    path("api/dictionaries/export/", export_dictionaries, name="itsm-dictionary-export"),
    path("api/dictionaries/import/", import_dictionaries, name="itsm-dictionary-import"),
    path("api/workflows/", workflows, name="itsm-workflows"),
    path("api/workflows/<int:workflow_id>/design/", workflow_design, name="itsm-workflow-design"),
    path("api/workflows/<int:workflow_id>/publish/", publish_workflow, name="itsm-workflow-publish"),
    path("api/workflow_types/", workflow_types, name="itsm-workflow-types"),
    path("api/workflow_variables/", workflow_variables, name="itsm-workflow-variables"),
    path("api/handler_groups/", handler_groups, name="itsm-handler-groups"),
    path("api/notify_templates/", notify_templates, name="itsm-notify-templates"),
    path("api/tickets/", tickets, name="itsm-tickets"),
    path("api/tickets/<int:ticket_id>/operate/", operate_ticket, name="itsm-ticket-operate"),
    path("api/tickets/<int:ticket_id>/logs/", ticket_logs, name="itsm-ticket-logs"),
]
