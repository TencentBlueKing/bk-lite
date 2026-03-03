import useApiClient from '@/utils/request';
import { TRAINJOB_MAP, SERVING_MAP } from '@/app/mlops/constants';
import type { 
  DatasetType,
  AnomalyDetectionReasonParams,
  TimeseriesPredictReasonParams,
  LogClusteringReasonParams,
  ClassificationReasonParams,
  ImageClassificationReasonParams,
  ObjectDetectionReasonParams
} from '@/app/mlops/types';


const useMlopsModelReleaseApi = () => {
  const {
    get,
    post,
    del,
    // put,
    patch
  } = useApiClient();

  // 获取能力发布列表
  const getServingList = async ({
    key,
    page,
    page_size,
    name,
  }: {
    key: DatasetType,
    page?: number,
    page_size?: number,
    name?: string
  }) => {
    const params = new URLSearchParams();
    if (page) params.append('page', String(page));
    if (page_size) params.append('page_size', String(page_size));
    if (name) params.append('name', name);
    return await get(`/mlops/${SERVING_MAP[key]}/?${params.toString()}`)
  };


  // 查询单个能力
  const getOneServingInfo = async (id: number, key: DatasetType) => {
    return await get(`/mlops/${SERVING_MAP[key]}/${id}/`);
  };

  // 查询模型版本列表
  const getModelVersionList = async (id: number, key: DatasetType) => {
    return await get(`mlops/${TRAINJOB_MAP[key]}/${id}/model_versions`);
  };

  // 新增能力发布
  const addAnomalyServings = async (params: {
    name: string;
    description: string;
    model_version: string;
    train_job: string;
    status: string;
  }) => {
    return await post(`/mlops/anomaly_detection_servings/`, params);
  };

  // 新增时序预测能力
  const addTimeseriesPredictServings = async (params: {
    name: string;
    description: string;
    model_version: string;
    train_job: string;
    status: string;
  }) => {
    return await post(`/mlops/timeseries_predict_servings/`, params);
  };

  // 新增日志聚类能力
  const addLogClusteringServings = async (params: {
    name: string;
    description: string;
    model_version: string;
    train_job: string;
    status: string;
  }) => {
    return await post(`/mlops/log_clustering_servings/`, params);
  };

  // 新增分类任务能力
  const addClassificationServings = async (params: {
    name: string;
    description: string;
    model_version: string;
    train_job: string;
    status: string;
  }) => {
    return await post(`/mlops/classification_servings/`, params);
  };

  // 新增图片分类任务能力
  const addImageClassificationServings = async (params: {
    name: string;
    description: string;
    model_version: string;
    train_job: string;
    status: string;
  }) => {
    return await post(`/mlops/image_classification_servings/`, params);
  };

  // 新增目标检测任务能力
  const addObjectDetectionServings = async (params: {
    name: string;
    description: string;
    model_version: string;
    train_job: string;
    status: string;
  }) => {
    return await post(`/mlops/object_detection_servings/`, params);
  };

  // 异常检测推理
  const anomalyDetectionReason = async (servingId: number, params: AnomalyDetectionReasonParams) => {
    return await post(`/mlops/anomaly_detection_servings/${servingId}/predict/`, params);
  };

  // 时序预测推理
  const timeseriesPredictReason = async (servingId: number, params: TimeseriesPredictReasonParams) => {
    return await post(`/mlops/timeseries_predict_servings/${servingId}/predict/`, params);
  };

  // 日志聚类推理
  const logClusteringReason = async (servingId: number, params: LogClusteringReasonParams) => {
    return await post(`/mlops/log_clustering_servings/${servingId}/predict/`, params);
  };

  // 分类任务推理
  const classificationReason = async (servingId: number, params: ClassificationReasonParams) => {
    return await post(`/mlops/classification_servings/${servingId}/predict/`, params);
  };

  // 图片分类推理
  const imageClassificationReason = async (servingId: number, params: ImageClassificationReasonParams) => {
    return await post(`/mlops/image_classification_servings/${servingId}/predict/`, params);
  };

  // 目标检测推理
  const objectDetectionReason = async (servingId: number, params: ObjectDetectionReasonParams) => {
    return await post(`/mlops/object_detection_servings/${servingId}/predict/`, params);
  };

  // 编辑能力发布
  const updateAnomalyServings = async (id: number, params: {
    name?: string;
    description?: string;
    model_version?: string;
    train_job?: string;
    status?: string;
  }) => {
    return await patch(`/mlops/anomaly_detection_servings/${id}/`, params);
  };

  // 编辑时序预测能力
  const updateTimeSeriesPredictServings = async (id: number, params: {
    name?: string;
    description?: string;
    model_version?: string;
    train_job?: string;
    status?: string;
  }) => {
    return await patch(`/mlops/timeseries_predict_servings/${id}/`, params);
  };

  // 编辑日志聚类能力
  const updateLogClusteringServings = async (id: number, params: {
    name?: string;
    description?: string;
    model_version?: string;
    train_job?: string;
    status?: string;
  }) => {
    return await patch(`/mlops/log_clustering_servings/${id}/`, params);
  };

  // 编辑分类任务能力
  const updateClassificationServings = async (id: number, params: {
    name?: string;
    description?: string;
    model_version?: string;
    train_job?: string;
    status?: string;
  }) => {
    return await patch(`/mlops/classification_servings/${id}/`, params)
  };

  // 编辑图片分类任务能力
  const updateImageClassificationServings = async (id: number, params: {
    name?: string;
    description?: string;
    model_version?: string;
    train_job?: string;
    status?: string;
  }) => {
    return await patch(`/mlops/image_classification_servings/${id}/`, params)
  };

  // 编辑目标检测任务能力
  const updateObjectDetectionServings = async (id: number, params: {
    name?: string;
    description?: string;
    model_version?: string;
    train_job?: string;
    status?: string;
  }) => {
    return await patch(`/mlops/object_detection_servings/${id}/`, params)
  };

  // 删除能力发布
  const deleteServing = async (id: number, key: DatasetType) => {
    return await del(`/mlops/${SERVING_MAP[key]}/${id}/`);
  };

  // 启动服务容器
  const startServingContainer = async (id: number, key: DatasetType) => {
    return await post(`/mlops/${SERVING_MAP[key]}/${id}/start`);
  };

  // 停止服务容器
  const stopServingContainer = async (id: number, key: DatasetType) => {
    return await post(`/mlops/${SERVING_MAP[key]}/${id}/stop`);
  };


  return {
    getModelVersionList,
    getServingList,
    getOneServingInfo,

    addAnomalyServings,
    addLogClusteringServings,
    addTimeseriesPredictServings,
    addClassificationServings,
    addImageClassificationServings,
    addObjectDetectionServings,
    anomalyDetectionReason,
    timeseriesPredictReason,
    logClusteringReason,
    classificationReason,
    imageClassificationReason,
    objectDetectionReason,
    updateAnomalyServings,
    updateTimeSeriesPredictServings,
    updateLogClusteringServings,
    updateClassificationServings,
    updateImageClassificationServings,
    updateObjectDetectionServings,
    deleteServing,
    startServingContainer,
    stopServingContainer
  };
};

export default useMlopsModelReleaseApi;
