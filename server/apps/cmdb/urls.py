from rest_framework import routers

from apps.cmdb.views.change_record import ChangeRecordViewSet
from apps.cmdb.views.classfication import ClassificationViewSet
from apps.cmdb.views.instance import InstanceViewSet
from apps.cmdb.views.model import ModelViewSet
from apps.cmdb.views.collect import CollectModelViewSet, MidModelViewSet

router = routers.DefaultRouter()
router.register(r"api/classification", ClassificationViewSet, basename="classification")
router.register(r"api/model", ModelViewSet, basename="model")
router.register(r"api/instance", InstanceViewSet, basename="instance")
router.register(r"api/change_record", ChangeRecordViewSet, basename="change_record")
router.register(r"api/collect", CollectModelViewSet, basename="collect")
router.register(r"api/oid", MidModelViewSet, basename="oid")

urlpatterns = router.urls
