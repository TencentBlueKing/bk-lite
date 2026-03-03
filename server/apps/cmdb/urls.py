from rest_framework import routers

from apps.cmdb.views.change_record import ChangeRecordViewSet
from apps.cmdb.views.classification import ClassificationViewSet
from apps.cmdb.views.instance import InstanceViewSet
from apps.cmdb.views.model import ModelViewSet
from apps.cmdb.views.collect import CollectModelViewSet, OidModelViewSet
from apps.cmdb.views.field_group import FieldGroupViewSet
from apps.cmdb.views.user_personal_config import UserPersonalConfigViewSet

router = routers.DefaultRouter()
router.register(r"api/classification", ClassificationViewSet, basename="classification")
router.register(r"api/model", ModelViewSet, basename="model")
router.register(r"api/instance", InstanceViewSet, basename="instance")
router.register(r"api/change_record", ChangeRecordViewSet, basename="change_record")
router.register(r"api/collect", CollectModelViewSet, basename="collect")
router.register(r"api/oid", OidModelViewSet, basename="oid")
router.register(r"api/field_groups", FieldGroupViewSet, basename="field_groups")
router.register(r"api/user_configs", UserPersonalConfigViewSet, basename="user_configs")

urlpatterns = router.urls
