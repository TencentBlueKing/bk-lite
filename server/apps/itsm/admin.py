from django.contrib import admin

from apps.itsm.models import (
    DataDictionary,
    DataDictionaryItem,
    FormModel,
    FormVersion,
    HandlerGroup,
    ItsmSetting,
    NotifyTemplate,
    Service,
    ServiceCatalog,
    StatusTransition,
    TicketStatus,
    Workflow,
    WorkflowType,
    WorkflowVariable,
    WorkflowVersion,
)

admin.site.register(FormModel)
admin.site.register(FormVersion)
admin.site.register(DataDictionary)
admin.site.register(DataDictionaryItem)
admin.site.register(WorkflowType)
admin.site.register(Workflow)
admin.site.register(WorkflowVersion)
admin.site.register(WorkflowVariable)
admin.site.register(HandlerGroup)
admin.site.register(TicketStatus)
admin.site.register(StatusTransition)
admin.site.register(NotifyTemplate)
admin.site.register(ServiceCatalog)
admin.site.register(Service)
admin.site.register(ItsmSetting)
