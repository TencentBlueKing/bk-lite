from django.contrib import admin

from apps.node_mgmt.models.sidecar import Node, Collector, CollectorConfiguration, Action, SidecarApiToken
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv


@admin.register(CloudRegion)
class CloudRegionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'introduction')
    search_fields = ('name', 'introduction')


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'ip', 'operating_system', 'collector_configuration_directory')
    search_fields = ('name', 'ip', 'operating_system')


@admin.register(Collector)
class CollectorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'service_type', 'node_operating_system', 'executable_path')
    search_fields = ('name', 'service_type', 'node_operating_system')


@admin.register(CollectorConfiguration)
class CollectorConfigurationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'collector')
    search_fields = ('name', 'collector__name')


@admin.register(Action)
class ActionAdmin(admin.ModelAdmin):
    list_display = ('node', 'action')
    search_fields = ('node__name',)


@admin.register(SidecarApiToken)
class SidecarApiTokenAdmin(admin.ModelAdmin):
    list_display = ('token',)
    search_fields = ('token',)


@admin.register(SidecarEnv)
class SidecarEnvAdmin(admin.ModelAdmin):
    list_display = ('key', 'value')
    search_fields = ('key', 'value')
