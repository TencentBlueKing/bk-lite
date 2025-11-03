from rest_framework import routers

from apps.mlops.views.anomaly_detection import *
from apps.mlops.views.timeseries_predict import *
from apps.mlops.views.log_clustering import *
from apps.mlops.views.rasa import *
from apps.mlops.views.classification import *

router = routers.DefaultRouter()

# 异常检测
router.register(r'anomaly_detection_datasets', AnomalyDetectionDatasetViewSet, basename='anomaly_detection_datasets')
router.register(r'anomaly_detection_train_data', AnomalyDetectionTrainDataViewSet, basename='anomaly_detection_train_data')
router.register(r'anomaly_detection_train_jobs', AnomalyDetectionTrainJobViewSet, basename='anomaly_detection_train_jobs')
router.register(r'anomaly_detection_servings', AnomalyDetectionServingViewSet, basename='anomaly_detection_servings')

# 时间序列预测
router.register(r'timeseries_predict_datasets', TimeSeriesPredictDatasetViewSet, basename='timeseries_predict_datasets')
router.register(r'timeseries_predict_train_data', TimeSeriesPredictTrainDataViewSet, basename='timeseries_predict_train_data')
router.register(r'timeseries_predict_train_jobs', TimeSeriesPredictTrainJobViewSet, basename='timeseries_predict_train_jobs')
router.register(r'timeseries_predict_train_history', TimeSeriesPredictTrainHistoryViewSet, basename='timeseries_predict_train_history')
router.register(r'timeseries_predict_servings', TimeSeriesPredictServingViewSet, basename='timeseries_predict_servings')

# 分类任务
router.register(r'classification_datasets', ClassificationDatasetViewSet, basename='classification_datasets')
router.register(r'classification_train_data', ClassificationTrainDataViewSet, basename='classification_train_data')
router.register(r'classification_train_jobs', ClassificationTrainJobViewSet, basename='classification_train_jobs')
router.register(r'classification_train_history', ClassificationTrainHistoryViewSet, basename='classification_train_history')
router.register(r'classification_servings', ClassificationServingViewSet, basename='classification_servings')

# 日志聚类
router.register(r'log_clustering_datasets', LogClusteringDatasetViewSet, basename='log_clustering_datasets')
router.register(r'log_clustering_train_data', LogClusteringTrainDataViewSet, basename='log_clustering_train_data')
router.register(r'log_clustering_train_jobs', LogClusteringTrainJobViewSet, basename='log_clustering_train_jobs')
router.register(r'log_clustering_train_history', LogClusteringTrainHistoryViewSet, basename='log_clustering_train_history')
router.register(r'log_clustering_servings', LogClusteringServingViewSet, basename='log_clustering_servings')

# Rasa
router.register(r'rasa_datasets', RasaDatasetViewSet, basename='rasa_datasets')
router.register(r'rasa_intent', RasaIntentViewSet, basename='rasa_intent')
router.register(r'rasa_response', RasaResponseViewSet, basename='rasa_response')
router.register(r'rasa_rule', RasaRuleViewSet, basename='rasa_rule')
router.register(r'rasa_story', RasaStoryViewSet, basename='rasa_story')
router.register(r'rasa_entity', RasaEntityViewSet, basename='rasa_entity')
router.register(r'rasa_slot', RasaSlotViewSet, basename='rasa_slot')
router.register(r'rasa_form', RasaFormViewSet, basename='rasa_form')
router.register(r'rasa_action', RasaActionViewSet, basename='rasa_action')
router.register(r'rasa_pipelines', RasaPipelineViewSet, basename='rasa_pipelines')

urlpatterns = router.urls
