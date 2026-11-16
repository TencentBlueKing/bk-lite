from django.urls import path, include
urlpatterns = [path('openapi/v1/', include('apps.core.openapi.urls'))] + [
    path(f'api/v1/{name}/', include(f'apps.{name}.urls'))
    for name in ['core','system_mgmt','node_mgmt','console_mgmt','log','apm']
]
