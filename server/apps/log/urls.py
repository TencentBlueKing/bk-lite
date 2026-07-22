from rest_framework import routers

from apps.log.views.collect_config import CollectConfigViewSet, CollectInstanceViewSet, CollectTypeViewSet
from apps.log.views.extractor import LogExtractorViewSet
from apps.log.views.k8s_collect import K8sCollectViewSet
from apps.log.views.log_group import LogGroupViewSet
from apps.log.views.node import NodeViewSet
from apps.log.views.open_api_k8s import K8sOpenAPIViewSet
from apps.log.views.policy import AlertViewSet, EventRawDataViewSet, EventViewSet, PolicyViewSet
from apps.log.views.search import LogSearchViewSet, SearchConditionViewSet
from apps.log.views.system_mgmt import SystemMgmtView
from apps.log.views.system_vector import SystemVectorConfigViewSet

router = routers.DefaultRouter()

router.register(r"collect_types", CollectTypeViewSet, basename="collect_type")
router.register(r"collect_instances", CollectInstanceViewSet, basename="collect_instance")
router.register(r"collect_configs", CollectConfigViewSet, basename="collect_config")
router.register(r"k8s_collect", K8sCollectViewSet, basename="k8s_collect")
router.register(r"node_mgmt", NodeViewSet, basename="node_mgmt")
router.register(r"log_group", LogGroupViewSet, basename="log_group")
router.register(r"search", LogSearchViewSet, basename="log_search")
router.register(r"search_conditions", SearchConditionViewSet, basename="search_condition")

# 策略相关路由
router.register(r"policy", PolicyViewSet, basename="policy")
router.register(r"alert", AlertViewSet, basename="alert")
router.register(r"event", EventViewSet, basename="event")
router.register(r"event_raw_data", EventRawDataViewSet, basename="event_raw_data")
router.register(r"system_mgmt", SystemMgmtView, basename="log_system_mgmt")
router.register(r"open_api/k8s", K8sOpenAPIViewSet, basename="log_k8s_open_api")
router.register(r"open_api/system_vector", SystemVectorConfigViewSet, basename="log-system-vector")
router.register(r"log_extractors", LogExtractorViewSet, basename="log-extractor")

urlpatterns = router.urls
