import useApiClient from '@/utils/request';
import { TRAINJOB_MAP } from '@/app/mlops/constants';

interface TrainTaskParams {
  name: string;
  description?: string;
  status: string;
  algorithm: string;
  train_data_id: number;
  val_data_id: number;
  text_data_id: number;
  max_evals: 0;
  hyperopt_config: object;
  windows_size?: number;
}

interface RasaPipelinesProps {
  name: string;
  datasets: number[];
  dataset_names: string[];
  config: {
    pipeline: any;
    policies: any;
  };
  datasets_detail?: any[];
  [key: string]: any
}



const useMlopsTaskApi = () => {
  const {
    get,
    post,
    // put,
    del,
    patch
  } = useApiClient();

  // 获取异常检测训练任务列表
  const getAnomalyTaskList = async ({
    name = '',
    page = 1,
    page_size = -1
  }: {
    name?: string,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/anomaly_detection_train_jobs/?name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 获取Rasa流水线
  const getRasaPipelines = async ({
    name = '',
    page = 1,
    page_size = -1
  }: {
    name?: string,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/rasa_pipelines/?name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 获取日志聚类训练任务
  const getLogClusteringTaskList = async ({
    name = '',
    page = 1,
    page_size = -1
  }: {
    name?: string,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/log_clustering_train_jobs/?name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 获取时序预测训练任务
  const getTimeSeriesTaskList = async ({
    name = '',
    page = 1,
    page_size = -1
  }: {
    name?: string,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/timeseries_predict_train_jobs/?name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 获取分类任务训练任务
  const getClassificationTaskList = async ({
    name = '',
    page = 1,
    page_size = -1
  }: {
    name?: string,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/classification_train_jobs/?name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 查询指定的异常检测任务
  const getOneAnomalyTask = async (id: number | string) => {
    return await get(`/mlops/anomaly_detection_train_jobs/${id}`)
  };

  // 查询指定Rasa流水线
  const getOneRasaTask = async (id: number | string) => {
    return await get(`/mlops/rasa_pipelines/${id}`);
  };

  // 查询指定日志聚类训练任务
  const getOneLogClusteringTask = async (id: number | string) => {
    return await get(`/mlops/log_clustering_train_jobs/${id}`)
  };

  // 查询指定时序预测训练任务
  const getOneTimeSeriesTask = async (id: number | string) => {
    return await get(`/mlops/timeseries_predict_train_jobs/${id}`)
  };

  // 查询指定分类任务训练任务
  const getOneClassification = async (id: number | string) => {
    return await get(`/mlops/classification_train_jobs/${id}`);
  };

  // 获取训练状态数据
  const getTrainTaskState = async (id: number, activeTap: string) => {
    return await get(`/mlops/${TRAINJOB_MAP[activeTap]}/${id}/runs_data_list/`)
  };

  // 获取日志聚类训练历史记录
  const getLogClusteringHistories = async (id: number) => {
    return await get(`/mlops/log_clustering_train_history/${id}`);
  };

  // 获取时序预测训练历史记录
  const getTimeSeriesHistories = async (id: number) => {
    return await get(`/mlops/timeseries_predict_train_history/${id}`);
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
  const addAnomalyTrainTask = async (params: TrainTaskParams) => {
    return await post(`/mlops/anomaly_detection_train_jobs/`, params)
  };

  // 新建Rasa训练流水线
  const addRasaTrainTask = async (params: RasaPipelinesProps) => {
    return await post(`/mlops/rasa_pipelines/`, params);
  };

  // 新建日志聚类训练任务
  const addLogClusteringTrainTask = async (params: TrainTaskParams) => {
    return await post(`/mlops/log_clustering_train_jobs/`, params)
  };

  // 新建时序预测训练任务
  const addTimeSeriesTrainTask = async (params: TrainTaskParams) => {
    return await post(`/mlops/timeseries_predict_train_jobs/`, params)
  };

  // 新建分类任务训练任务
  const addClassificationTrainTask = async (params: TrainTaskParams) => {
    return await post(`/mlops/classification_train_jobs`, params);
  };

  // 启动异常检测训练任务
  const startAnomalyTrainTask = async (id: number | string) => {
    return await post(`/mlops/anomaly_detection_train_jobs/${id}/train/`);
  };

  // 启动日志聚类训练任务
  const startLogClusteringTrainTask = async (id: number | string) => {
    return await post(`/mlops/log_clustering_train_jobs/${id}/train/`);
  };

  // 启动时序预测训练任务
  const startTimeSeriesTrainTask = async (id: number | string) => {
    return await post(`/mlops/timeseries_predict_train_jobs/${id}/train/`);
  };

  // 启动分类任务训练任务
  const startClassificationTrainTask = async (id: number | string) => {
    return await post(`/mlops/classification_train_jobs/${id}/train/`);
  };

  // 编辑异常检测训练任务
  const updateAnomalyTrainTask = async (id: string, params: TrainTaskParams) => {
    return await patch(`/mlops/anomaly_detection_train_jobs/${id}/`, params);
  };

  // 编辑Rasa训练任务
  const updateRasaPipelines = async (id: string, params: RasaPipelinesProps) => {
    return await patch(`/mlops/rasa_pipelines/${id}/`, params);
  };

  // 编辑日志聚类训练任务
  const updateLogClusteringTrainTask = async (id: string, params: TrainTaskParams) => {
    return await patch(`/mlops/log_clustering_train_jobs/${id}/`, params);
  };

  // 编辑时序预测训练任务
  const updateTimeSeriesTrainTask = async (id: string, params: TrainTaskParams) => {
    return await patch(`/mlops/timeseries_predict_train_jobs/${id}/`, params);
  };

  // 编辑分类任务训练任务
  const updateClassificationTrainTask = async (id: string, params: TrainTaskParams) => {
    return await patch(`/mlops/classification_train_jobs/${id}/`, params);
  };

  // 删除异常检测训练任务
  const deleteAnomalyTrainTask = async (id: string) => {
    return await del(`/mlops/anomaly_detection_train_jobs/${id}/`);
  };

  // 删除Rasa训练流水线
  const deleteRasaPipelines = async (id: string) => {
    return await del(`/mlops/rasa_pipelines/${id}`);
  };

  // 删除日志聚类训练任务
  const deleteLogClusteringTrainTask = async (id: string) => {
    return await del(`/mlops/log_clustering_train_jobs/${id}/`);
  };

  // 删除时序预测训练任务
  const deleteTimeSeriesTrainTask = async (id: string) => {
    return await del(`/mlops/timeseries_predict_train_jobs/${id}/`);
  };

  // 删除分类任务训练任务
  const deleteClassificationTrainTask = async (id: string) => {
    return await del(`/mlops/classification_train_jobs/${id}/`);
  };

  // 获取训练所用的数据集数据
  const getTrainTaskFile = async (id: string, tap: string) => {
    return await get(`/mlops/${TRAINJOB_MAP[tap]}/${id}/get_file`);
  };

  return {
    getTrainTaskFile,
    getAnomalyTaskList,
    getOneAnomalyTask,
    getTrainTaskState,
    getTrainTaskMetrics,
    getTrainTaskMetricsDetail,
    getRasaPipelines,
    getLogClusteringTaskList,
    getLogClusteringHistories,
    getTimeSeriesTaskList,
    getTimeSeriesHistories,
    getOneLogClusteringTask,
    getOneRasaTask,
    getOneTimeSeriesTask,
    getClassificationTaskList,
    getOneClassification,
    addAnomalyTrainTask,
    addRasaTrainTask,
    addLogClusteringTrainTask,
    addTimeSeriesTrainTask,
    addClassificationTrainTask,
    startAnomalyTrainTask,
    startLogClusteringTrainTask,
    startTimeSeriesTrainTask,
    startClassificationTrainTask,
    updateAnomalyTrainTask,
    updateRasaPipelines,
    updateLogClusteringTrainTask,
    updateTimeSeriesTrainTask,
    updateClassificationTrainTask,
    deleteAnomalyTrainTask,
    deleteRasaPipelines,
    deleteLogClusteringTrainTask,
    deleteTimeSeriesTrainTask,
    deleteClassificationTrainTask
  }

};

export default useMlopsTaskApi;