import useApiClient from '@/utils/request';
import { TRAINJOB_MAP } from '@/app/mlops/constants';
import type { 
  DatasetType, 
  DatasetRelease,
  TrainJob,
  CreateTrainJobParams,
  UpdateTrainJobParams
} from '@/app/mlops/types';


const useMlopsTaskApi = () => {
  const {
    get,
    post,
    // put,
    del,
    patch
  } = useApiClient();

  // 获取训练任务列表
  const getTrainJobList = async ({
    key,
    name = '',
    page = 1,
    page_size = -1
  }: {
    key: DatasetType,
    name?: string,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/${TRAINJOB_MAP[key]}/?name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 查询指定的训练任务
  const getOneTrainJobInfo = async (id: number | string, key: DatasetType) => {
    return await get(`/mlops/${TRAINJOB_MAP[key]}/${id}`);
  };

  // 获取训练状态数据
  const getTrainTaskState = async (id: number, activeTap: string) => {
    return await get(`/mlops/${TRAINJOB_MAP[activeTap]}/${id}/runs_data_list/`)
  };

  // 获取状态指标
  const getTrainTaskMetrics = async (id: string, activeTap: string) => {
    return await get(`/mlops/${TRAINJOB_MAP[activeTap]}/runs_metrics_list/${id}`)
  };

  // 获取具体指标信息
  const getTrainTaskMetricsDetail = async (id: string, metrics_name: string, activeTap: string) => {
    return await get(`/mlops/${TRAINJOB_MAP[activeTap]}/runs_metrics_history/${id}/${metrics_name}`);
  };

  // 新建异常检测训练任务
  const addAnomalyTrainTask = async (params: CreateTrainJobParams): Promise<TrainJob> => {
    return await post(`/mlops/anomaly_detection_train_jobs/`, params)
  };

  // 新建日志聚类训练任务
  const addLogClusteringTrainTask = async (params: CreateTrainJobParams): Promise<TrainJob> => {
    return await post(`/mlops/log_clustering_train_jobs/`, params)
  };

  // 新建时序预测训练任务
  const addTimeSeriesTrainTask = async (params: CreateTrainJobParams): Promise<TrainJob> => {
    return await post(`/mlops/timeseries_predict_train_jobs/`, params)
  };

  // 新建分类任务训练任务
  const addClassificationTrainTask = async (params: CreateTrainJobParams): Promise<TrainJob> => {
    return await post(`/mlops/classification_train_jobs`, params);
  };

  // 新建图片分类训练任务
  const addImageClassificationTrainTask = async (params: CreateTrainJobParams): Promise<TrainJob> => {
    return await post(`/mlops/image_classification_train_jobs/`, params);
  };

  // 新建目标检测训练任务
  const addObjectDetectionTrainTask = async (params: CreateTrainJobParams): Promise<TrainJob> => {
    return await post(`/mlops/object_detection_train_jobs/`, params);
  };

  // 启动训练
  const startTrainTask = async (id: number | string, key: DatasetType) => {
    return await post(`/mlops/${TRAINJOB_MAP[key]}/${id}/train/`);
  };

  // 编辑异常检测训练任务
  const updateAnomalyTrainTask = async (id: string, params: UpdateTrainJobParams): Promise<TrainJob> => {
    return await patch(`/mlops/anomaly_detection_train_jobs/${id}/`, params);
  };

  // 编辑日志聚类训练任务
  const updateLogClusteringTrainTask = async (id: string, params: UpdateTrainJobParams): Promise<TrainJob> => {
    return await patch(`/mlops/log_clustering_train_jobs/${id}/`, params);
  };

  // 编辑时序预测训练任务
  const updateTimeSeriesTrainTask = async (id: string, params: UpdateTrainJobParams): Promise<TrainJob> => {
    return await patch(`/mlops/timeseries_predict_train_jobs/${id}/`, params);
  };

  // 编辑分类任务训练任务
  const updateClassificationTrainTask = async (id: string, params: UpdateTrainJobParams): Promise<TrainJob> => {
    return await patch(`/mlops/classification_train_jobs/${id}/`, params);
  };

  // 编辑图片分类训练任务
  const updateImageClassificationTrainTask = async (id: string, params: UpdateTrainJobParams): Promise<TrainJob> => {
    return await patch(`/mlops/image_classification_train_jobs/${id}/`, params);
  };

  // 编辑目标检测训练任务
  const updateObjectDetectionTrainTask = async (id: string, params: UpdateTrainJobParams): Promise<TrainJob> => {
    return await patch(`/mlops/object_detection_train_jobs/${id}/`, params);
  };

  // 删除训练任务
  const deleteTrainTask = async (id: string, key: DatasetType) => {
    return await del(`/mlops/${TRAINJOB_MAP[key]}/${id}/`);
  };

  // 创建数据集版本发布（标准方式，从数据集管理页面）
  const createDatasetRelease = async (
    key: DatasetType,
    params: {
      dataset: number;
      version: string;
      name?: string;
      description?: string;
      train_file_id: number;
      val_file_id: number;
      test_file_id: number;
    }
  ) => {
    return await post(`/mlops/${key}_dataset_releases/`, params);
  };

  // 获取数据集版本列表
  const getDatasetReleases = async (
    key: DatasetType,
    params?: { dataset?: number; page?: number; page_size?: number }
  ) => {
    const queryParams = new URLSearchParams();
    if (params?.dataset) queryParams.append('dataset', params.dataset.toString());
    if (params?.page) queryParams.append('page', params.page.toString());
    if (params?.page_size) queryParams.append('page_size', params.page_size.toString());
    return await get(`/mlops/${key}_dataset_releases/?${queryParams.toString()}`);
  };

  // 获取指定数据集版本信息
  const getDatasetReleaseByID = async (key: DatasetType, id: number | string): Promise<DatasetRelease> => {
    return await get(`/mlops/${key}_dataset_releases/${id}/`);
  };

  // 归档数据集版本
  const archiveDatasetRelease = async (key: DatasetType, id: string) => {
    return await post(`/mlops/${key}_dataset_releases/${id}/archive/`);
  };

  // 已归档数据集版本恢复发布
  const unarchiveDatasetRelease = async (key: DatasetType, id: string) => {
    return await post(`/mlops/${key}_dataset_releases/${id}/unarchive/`);
  };

  // 删除数据集版本
  const deleteDatasetRelease = async (key: DatasetType, id: string) => {
    return await del(`/mlops/${key}_dataset_releases/${id}/`);
  };

  // 获取时间序列模型文件URL
  const getTimeseriesPredictModelURL = async (run_id: string) => {
    return await get(`/mlops/timeseries_predict_train_jobs/download_model/${run_id}/`);
  };



  return {
    getTrainJobList,
    getOneTrainJobInfo,
    getTrainTaskState,
    getTrainTaskMetrics,
    getTrainTaskMetricsDetail,
    getDatasetReleaseByID,
    getTimeseriesPredictModelURL,
    addAnomalyTrainTask,
    addLogClusteringTrainTask,
    addTimeSeriesTrainTask,
    addClassificationTrainTask,
    addImageClassificationTrainTask,
    addObjectDetectionTrainTask,
    startTrainTask,
    updateAnomalyTrainTask,
    updateLogClusteringTrainTask,
    updateTimeSeriesTrainTask,
    updateClassificationTrainTask,
    updateImageClassificationTrainTask,
    updateObjectDetectionTrainTask,
    deleteTrainTask,
    createDatasetRelease,
    getDatasetReleases,
    archiveDatasetRelease,
    unarchiveDatasetRelease,
    deleteDatasetRelease
  }

};

export default useMlopsTaskApi;