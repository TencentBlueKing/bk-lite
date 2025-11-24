import useApiClient from "@/utils/request";
import { TrainDataParams } from '@/app/mlops/types/manage';

interface TrainDataBrochure {
  dataset: number;
  name: string;
  train_data: (TrainDataParams | string)[];
  metadata?: object;
  is_train_data?: boolean;
  is_val_data?: boolean;
  is_test_data?: boolean;
}

const useMlopsManageApi = () => {
  const {
    get,
    post,
    put,
    del,
    patch
  } = useApiClient();

  // 获取异常检测数据集列表
  const getAnomalyDatasetsList = async ({
    page = 1,
    page_size = -1
  }: {
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/anomaly_detection_datasets/?page=${page}&page_size=${page_size}`);
  };

  // 获取Rasa数据集列表
  const getRasaDatasetsList = async ({
    page = 1,
    page_size = -1
  }: {
    page?: number;
    page_size?: number
  }) => {
    return await get(`/mlops/rasa_datasets/?page=${page}&page_size=${page_size}`);
  };

  // 获取日志聚类数据集列表
  const getLogClusteringList = async ({
    page = 1,
    page_size = -1
  }: {
    page?: number;
    page_size?: number
  }) => {
    return await get(`/mlops/log_clustering_datasets/?page=${page}&page_size=${page_size}`);
  };

  // 获取时序预测数据集列表
  const getTimeSeriesPredictList = async ({
    page = 1,
    page_size = -1
  }: {
    page?: number;
    page_size?: number
  }) => {
    return await get(`/mlops/timeseries_predict_datasets/?page=${page}&page_size=${page_size}`);
  };

  // 获取分类任务数据集列表
  const getClassificationDatasetsList = async ({
    page = 1,
    page_size = -1
  }: {
    page?: number;
    page_size?: number
  }) => {
    return await get(`/mlops/classification_datasets/?page=${page}&page_size=${page_size}`)
  };

  // 获取图片分类任务数据集列表
  const getImageClassificationDatasetsList = async ({
    page = 1,
    page_size = -1
  }: {
    page?: number;
    page_size?: number
  }) => {
    return await get(`/mlops/image_classification_datasets/?page=${page}&page_size=${page_size}`)
  };

  // 获取目标检测任务数据集列表
  const getObjectDetectionDatasetsList = async ({
    page = 1,
    page_size = -1,
  }: {
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/object_detection_datasets/?page=${page}&page_size=${page_size}`);
  };

  // 获取Rasa意图列表
  const getRasaIntentFileList = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1
  }: {
    name?: string;
    dataset: string | number;
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/rasa_intent/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`)
  };

  // 获取Rasa响应列表
  const getRasaResponseFileList = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1,
  }: {
    name?: string,
    dataset: string | number,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/rasa_response/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 获取Rasa规则列表
  const getRasaRuleFileList = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1,
  }: {
    name?: string,
    dataset: string | number,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/rasa_rule/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 获取Rasa故事列表
  const getRasaStoryFileList = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1,
  }: {
    name?: string,
    dataset: string | number,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/rasa_story/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 获取Rasa实体列表
  const getRasaEntityList = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1,
  }: {
    name?: string,
    dataset: string | number,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/rasa_entity/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 获取Rasa 实体数
  const getRasaEntityCount = async () => {
    return await get(`/mlops/rasa_entity/count`)
  };

  // 获取Rasa槽列表
  const getRasaSlotList = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1,
  }: {
    name?: string,
    dataset: string | number,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/rasa_slot/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`)
  };

  // 获取Rasa表单列表
  const getRasaFormList = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1,
  }: {
    name?: string,
    dataset: string | number,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/rasa_form/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`)
  };

  // 获取Rasa响应动作列表
  const getRasaActionList = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1
  }: {
    name?: string;
    dataset: string | number;
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/rasa_action/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`)
  };

  // 获取指定异常检测数据集详情
  const getOneAnomalyDataset = async (id: number) => {
    return await get(`/mlops/anomaly_detection_datasets/${id}/`);
  };

  // 获取指定日志聚类数据集详情
  const getOneLogClustering = async (id: number) => {
    return await get(`/mlops/log_clustering_datasets/${id}/`);
  };

  // 获取指定时序预测数据集详情
  const getOneTimeSeriesPredict = async (id: number) => {
    return await get(`/mlops/timeseries_predict_datasets/${id}/`);
  };

  // 获取指定分类任务数据集详情
  const getOneClassificationDataset = async (id: number) => {
    return await get(`/mlops/classification_datasets/${id}/`);
  };

  // 获取指定图片分类数据集详情
  const getOneImageClassificationDataset = async (id: number) => {
    return await get(`/mlops/image_classification_datasets/${id}/`);
  };

  // 获取指定目标检测数据集详情
  const getOneObjectDetectionDataset = async (id: number) => {
    return await get(`/mlops/object_detection_datasets/${id}`);
  };

  // 查询指定数据集下的样本列表
  const getAnomalyTrainData = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1
  }: {
    name?: string;
    dataset?: string | number;
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/anomaly_detection_train_data/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 查询指定日志聚类数据集下的样本列表
  const getLogClusteringTrainData = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1
  }: {
    name?: string;
    dataset?: string | number;
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/log_clustering_train_data/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 查询指定时序预测数据集下的样本文件
  const getTimeSeriesPredictTrainData = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1
  }: {
    name?: string;
    dataset?: string | number;
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/timeseries_predict_train_data/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`);
  };

  // 查询指定分类任务数据集下的样本文件
  const getClassificationTrainData = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1
  }: {
    name?: string;
    dataset?: string | number;
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/classification_train_data/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`)
  };

  // 查询指定图片分类任务数据集下的样本文件
  const getImageClassificationTrainData = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1
  }: {
    name?: string;
    dataset?: string | number;
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/image_classification_traindata/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`)
  };

  // 查询指定目标检测任务数据集下的样本文件
  const getObjectDetectionTrainData = async ({
    name = '',
    dataset,
    page = 1,
    page_size = -1
  }: {
    name?: string;
    dataset?: string | number;
    page?: number;
    page_size?: number;
  }) => {
    return await get(`/mlops/object_detection_traindata/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`)
  };

  // 获取指定异常检测样本的详情
  const getAnomalyTrainDataInfo = async (id: number | string, include_train_data?: boolean, include_metadata?: boolean) => {
    return await get(`/mlops/anomaly_detection_train_data/${id}?include_train_data=${include_train_data}&include_metadata=${include_metadata}`);
  };

  // 获取指定日志聚类样本的详情
  const getLogClusteringTrainDataInfo = async (id: number | string, include_train_data?: boolean, include_metadata?: boolean) => {
    return await get(`/mlops/log_clustering_train_data/${id}?include_train_data=${include_train_data}&include_metadata=${include_metadata}`);
  };

  // 获取指定时序预测样本的详情
  const getTimeSeriesPredictTrainDataInfo = async (id: number | string, include_train_data?: boolean, include_metadata?: boolean) => {
    return await get(`/mlops/timeseries_predict_train_data/${id}?include_train_data=${include_train_data}&include_metadata=${include_metadata}`);
  };

  // 获取指定分类任务样本的详情
  const getClassificationTrainDataInfo = async (id: number | string, include_train_data?: boolean, include_metadata?: boolean) => {
    return await get(`/mlops/classification_train_data/${id}?include_train_data=${include_train_data}&include_metadata=${include_metadata}`);
  };

  // 获取指定图片分类任务样本的详情
  const getImageClassificationTrainDataInfo = async (id: number | string, include_train_data?: boolean, include_metadata?: boolean) => {
    return await get(`/mlops/image_classification_traindata/${id}?include_train_data=${include_train_data}&include_metadata=${include_metadata}`)
  };

  // 获取指定目标检测任务样本的详情
  const getObjectDetectionTrainDataInfo = async (id: number | string, include_train_data?: boolean, include_metadata?: boolean) => {
    return await get(`/mlops/object_detection_traindata/${id}?include_train_data=${include_train_data}&include_metadata=${include_metadata}`)
  };

  // 新增异常检测数据集
  const addAnomalyDatasets = async (params: {
    name: string;
    description: string;
  }) => {
    return await post(`/mlops/anomaly_detection_datasets/`, params);
  };

  // 新增rasa数据集
  const addRasaDatasets = async (params: {
    name: string;
    description: string;
  }) => {
    return await post(`/mlops/rasa_datasets/`, params);
  };

  // 新增日志聚类数据集
  const addLogClusteringDatasets = async (params: {
    name: string;
    description: string;
  }) => {
    return await post(`/mlops/log_clustering_datasets/`, params);
  };

  // 新增时序预测数据集
  const addTimeSeriesPredictDatasets = async (params: {
    name: string;
    description: string;
  }) => {
    return await post(`/mlops/timeseries_predict_datasets/`, params);
  };

  // 新增分类任务数据集
  const addClassificationDatasets = async (params: {
    name: string;
    description: string;
  }) => {
    return await post(`/mlops/classification_datasets/`, params);
  };

  // 新增图片分类任务数据集
  const addImageClassificationDatasets = async (params: {
    name: string;
    description: string;
  }) => {
    return await post(`/mlops/image_classification_datasets`, params)
  };

  // 新增目标检测任务数据集
  const addObjectDetectionDataset = async (params: {
    name: string;
    description: string;
  }) => {
    return await post(`/mlops/object_detection_datasets`, params);
  };

  // 新增rasa意图
  const addRasaIntentFile = async (params: {
    name: string;
    dataset: number;
    example: string[]
  }) => {
    return await post(`/mlops/rasa_intent`, params);
  };

  // 新增Rasa响应
  const addRasaResponseFile = async (params: {
    name: string;
    dataset: number;
    example: string[]
  }) => {
    return await post(`/mlops/rasa_response`, params);
  };

  // 新增Rasa规则
  const addRasaRuleFile = async (params: {
    name: string;
    dataset: number;
    steps: {
      intent?: string;
      response?: string;
    }[]
  }) => {
    return await post(`/mlops/rasa_rule`, params);
  };

  // 新增Rasa故事
  const addRasaStoryFile = async (params: {
    name: string;
    dataset: number;
    steps: {
      intent?: string;
      response?: string;
    }[]
  }) => {
    return await post(`/mlops/rasa_story`, params);
  };

  // 新增Rasa实体
  const addRasaEntityFile = async (params: {
    name: string;
    dataset: number;
    entity_type: string;
    example: string[];
  }) => {
    return await post(`/mlops/rasa_entity`, params);
  };

  // 新增Rasa槽
  const addRasaSlotFile = async (params: {
    name: string;
    dataset: number;
    slot_type: string;
    is_apply: string;
  }) => {
    return await post(`/mlops/rasa_slot`, params);
  };

  // 新增Rasa表单
  const addRasaFormFile = async (params: {
    name: string;
    dataset: number;
    slots: {
      name: string;
      type: string;
      isRequired: boolean;
    }
  }) => {
    return await post(`/mlops/rasa_form`, params);
  };

  // 新增Rasa响应动作
  const addRasaActionFile = async (params: {
    name: string;
    dataset: number;
  }) => {
    return await post(`/mlops/rasa_action`, params);
  };

  // 新增异常数据检测集样本
  const addAnomalyTrainData = async (params: TrainDataBrochure) => {
    return await post(`/mlops/anomaly_detection_train_data`, params);
  };

  // 新增日志聚类数据集样本文件
  const addLogClusteringTrainData = async (params: TrainDataBrochure) => {
    return await post(`/mlops/log_clustering_train_data`, params);
  };

  // 新增时序预测样本文件
  const addTimeSeriesPredictTrainData = async (params: TrainDataBrochure) => {
    return await post(`/mlops/timeseries_predict_train_data`, params);
  };

  // 新增分类任务样本文件
  const addClassificationTrainData = async (params: TrainDataBrochure) => {
    return await post(`/mlops/classification_train_data`, params);
  };

  // 新增图片分类任务样本文件
  const addImageClassificationTrainData = async (params: FormData) => {
    return await post(`/mlops/image_classification_traindata`, params, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  };

  // 新增目标检测任务样本文件
  const addObjectDetectionTrainData = async (params: FormData) => {
    return await post(`/mlops/object_detection_traindata`, params, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  };

  // 更新异常检测数据集
  const updateAnomalyDatasets = async (id: number, params: {
    name: string;
    description: string;
  }) => {
    return await put(`/mlops/anomaly_detection_datasets/${id}`, params);
  };

  // 更新Rasa数据集
  const updateRasaDatasets = async (id: number, params: {
    name: string;
    description: string;
  }) => {
    return await put(`/mlops/rasa_datasets/${id}`, params);
  };

  // 更新日志聚类数据集
  const updateLogClustering = async (id: number, params: {
    name: string;
    description: string;
  }) => {
    return await put(`/mlops/log_clustering_datasets/${id}`, params);
  };

  // 更新时序预测数据集
  const updateTimeSeriesPredict = async (id: number, params: {
    name: string;
    description: string;
  }) => {
    return await put(`/mlops/timeseries_predict_datasets/${id}`, params);
  };

  // 更新分类任务数据集
  const updateClassificationDataset = async (id: number, params: {
    name: string;
    description: string;
  }) => {
    return await put(`/mlops/classification_datasets/${id}`, params);
  };

  // 更新图片分类任务数据集
  const updateImageClassificationDataset = async (id: number, params: {
    name: string;
    description: string;
  }) => {
    return await put(`/mlops/image_classification_datasets/${id}`, params);
  };

  // 更新目标检测任务数据集
  const updateObjectDetectionDataset = async (id: number, params: {
    name: string;
    description: string;
  }) => {
    return await put(`/mlops/object_detection_datasets/${id}`, params);
  };

  // 更新Rasa意图文件
  const updateRasaIntentFile = async (id: number, params: {
    name?: string;
    example: string[];
  }) => {
    return await put(`/mlops/rasa_intent/${id}`, params);
  };

  // 更新Rasa响应文件
  const updateRasaResponseFile = async (id: number, params: {
    name?: string;
    example: string[];
  }) => {
    return await put(`/mlops/rasa_response/${id}`, params);
  };

  // 更新Rasa规则文件
  const updateRasaRuleFile = async (id: number, params: {
    name: string;
    steps: {
      intent?: string;
      response?: string;
    }[];
  }) => {
    return await put(`/mlops/rasa_rule/${id}`, params);
  };

  // 更新Rasa故事文件
  const updateRasaStoryFile = async (id: number, params: {
    name: string;
    steps: {
      intent?: string;
      response?: string;
    }[];
  }) => {
    return await put(`/mlops/rasa_story/${id}`, params);
  };

  // 更新Rasa实体文件
  const updateRasaEntityFile = async (id: number, params: {
    name: string;
    entity_type: string;
    exmaple: string[];
  }) => {
    return await put(`/mlops/rasa_entity/${id}`, params);
  };

  // 更新Rasa槽文件
  const updateRasaSlotFile = async (id: number, params: {
    name: string;
    slot_type: string;
    is_apply: string;
  }) => {
    return await put(`/mlops/rasa_slot/${id}`, params);
  };

  // 更新Rasa表单文件
  const updateRasaFormFile = async (id: number, params: {
    name: string;
    slots: {
      name: string;
      type: string;
      isRequired: boolean;
    }
  }) => {
    return await put(`/mlops/rasa_form/${id}`, params)
  };

  // 更新Rasa响应动作文件
  const updateRasaActionFile = async (id: number, params: {
    name: string
  }) => {
    return await put(`/mlops/rasa_action/${id}`, params);
  };

  // 标注数据
  const labelingData = async (id: string, params: {
    metadata?: {
      anomaly_point: number[]
    },
    is_train_data?: boolean,
    is_val_data?: boolean,
    is_test_data?: boolean
  }) => {
    return await patch(`/mlops/anomaly_detection_train_data/${id}/`, params);
  };

  // 更新日志聚类数据集样本文件
  const updateLogClusteringTrainData = async (id: string, params: {
    is_train_data?: boolean,
    is_val_data?: boolean,
    is_test_data?: boolean,
    train_data?: any[]
  }) => {
    return await patch(`/mlops/log_clustering_train_data/${id}/`, params)
  };

  // 更新时序预测数据集样本文件
  const updateTimeSeriesPredictTrainData = async (id: string, params: {
    is_train_data?: boolean,
    is_val_data?: boolean,
    is_test_data?: boolean
  }) => {
    return await patch(`/mlops/timeseries_predict_train_data/${id}/`, params)
  };

  // 更新分类任务数据集样本文件
  const updateClassificationTrainData = async (id: string, params: {
    is_train_data?: boolean,
    is_val_data?: boolean,
    is_test_data?: boolean
  }) => {
    return await patch(`/mlops/classification_train_data/${id}`, params);
  };

  // 更新图片分类任务数据集样本文件
  const updateImageClassificationTrainData = async (
    id: string, 
    params: {
      is_train_data?: boolean,
      is_val_data?: boolean,
      is_test_data?: boolean,
      meta_data?: any
    } | FormData
  ) => {
    return await patch(`/mlops/image_classification_traindata/${id}`, params,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
  };

  // 更新目标检测任务数据集样本文件
  const updateObjectDetectionTrainData = async (id: string, params: {
    is_train_data?: boolean,
    is_val_data?: boolean,
    is_test_data?: boolean,
    meta_data?: any,
    train_data?: any
  } | FormData) => {
    return await patch(`/mlops/object_detection_traindata/${id}`, params,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
  };

  // 删除异常检测数据集
  const deleteAnomalyDatasets = async (id: number) => {
    return await del(`/mlops/anomaly_detection_datasets/${id}`);
  };

  // 删除Rasa数据集
  const deleteRasaDatasets = async (id: number) => {
    return await del(`/mlops/rasa_datasets/${id}`);
  };

  // 删除日志聚类数据集
  const deleteLogClustering = async (id: number) => {
    return await del(`/mlops/log_clustering_datasets/${id}`);
  };

  // 删除时序预测数据集
  const deleteTimeSeriesPredict = async (id: number) => {
    return await del(`/mlops/timeseries_predict_datasets/${id}`);
  };

  // 删除分类任务数据集
  const deleteClassificationDataset = async (id: number) => {
    return await del(`/mlops/classification_datasets/${id}`);
  };

  // 删除图片分类任务数据集
  const deleteImageClassificationDataset = async (id: number) => {
    return await del(`/mlops/image_classification_datasets/${id}`);
  };

  // 删除目标检测任务数据集
  const deleteObjectDetectionDataset = async (id: number) => {
    return await del(`/mlops/object_detection_datasets/${id}`);
  };

  // 删除指定Rasa意图文件
  const deleteRasaIntentFile = async (id: number) => {
    return await del(`/mlops/rasa_intent/${id}`);
  };

  // 删除指定Rasa响应文件
  const deleteRasaResponseFile = async (id: number) => {
    return await del(`/mlops/rasa_response/${id}`);
  };

  // 删除指定Rasa规则文件
  const deleteRasaRuleFile = async (id: number) => {
    return await del(`/mlops/rasa_rule/${id}`);
  };

  // 删除指定Rasa故事文件
  const deleteRasaStoryFile = async (id: number) => {
    return await del(`/mlops/rasa_story/${id}`);
  };

  // 删除指定Rasa实体文件
  const deleteRasaEntityFile = async (id: number) => {
    return await del(`/mlops/rasa_entity/${id}`);
  };

  // 删除指定Rasa槽文件
  const deleteRasaSlotFile = async (id: number) => {
    return await del(`/mlops/rasa_slot/${id}`);
  };

  // 删除指定Rasa表单文件
  const deleteRasaFormFile = async (id: number) => {
    return await del(`/mlops/rasa_form/${id}`);
  };

  // 删除指定Rasa响应动作文件
  const deleteRasaActionFile = async (id: number) => {
    return await del(`/mlops/rasa_action/${id}`);
  };

  // 删除训练数据
  const deleteAnomalyTrainData = async (id: number) => {
    return await del(`/mlops/anomaly_detection_train_data/${id}/`);
  };

  // 删除日志聚类训练文件
  const deleteLogClusteringTrainData = async (id: number) => {
    return await del(`/mlops/log_clustering_train_data/${id}/`);
  };

  // 删除时序预测训练文件
  const deleteTimeSeriesPredictTrainData = async (id: number) => {
    return await del(`/mlops/timeseries_predict_train_data/${id}/`);
  };

  // 删除分类任务训练文件
  const deleteClassificationTrainData = async (id: number) => {
    return await del(`mlops/classification_train_data/${id}/`);
  };

  // 删除图片分类任务训练文件
  const deleteImageClassificationTrainData = async (id: number) => {
    return await del(`/mlops/image_classification_traindata/${id}/`);
  };

  // 删除目标检测任务训练文件
  const deleteObjectDetectionTrainData = async (id: number) => {
    return await del(`/mlops/object_detection_traindata/${id}/`)
  };

  // 生成yolo数据集
  const generateYoloDataset = async (id: string) => {
    return await post(`/mlops/object_detection_traindata/${id}/generate_dataset/`);
  };

  return {
    getAnomalyDatasetsList,
    getRasaDatasetsList,
    getClassificationDatasetsList,
    getLogClusteringList,
    getTimeSeriesPredictList,
    getImageClassificationDatasetsList,
    getObjectDetectionDatasetsList,
    getOneAnomalyDataset,
    getAnomalyTrainData,
    getAnomalyTrainDataInfo,
    getRasaIntentFileList,
    getRasaResponseFileList,
    getRasaRuleFileList,
    getRasaStoryFileList,
    getRasaEntityList,
    getRasaEntityCount,
    getRasaSlotList,
    getRasaFormList,
    getRasaActionList,
    getOneLogClustering,
    getOneTimeSeriesPredict,
    getOneClassificationDataset,
    getOneImageClassificationDataset,
    getOneObjectDetectionDataset,
    getLogClusteringTrainData,
    getTimeSeriesPredictTrainData,
    getClassificationTrainData,
    getObjectDetectionTrainData,
    getLogClusteringTrainDataInfo,
    getTimeSeriesPredictTrainDataInfo,
    getClassificationTrainDataInfo,
    getImageClassificationTrainData,
    getImageClassificationTrainDataInfo,
    getObjectDetectionTrainDataInfo,
    addAnomalyDatasets,
    addLogClusteringDatasets,
    addTimeSeriesPredictDatasets,
    addClassificationDatasets,
    addObjectDetectionDataset,
    addRasaDatasets,
    addRasaIntentFile,
    addRasaResponseFile,
    addRasaRuleFile,
    addRasaEntityFile,
    addAnomalyTrainData,
    addLogClusteringTrainData,
    addTimeSeriesPredictTrainData,
    addClassificationTrainData,
    addImageClassificationDatasets,
    addObjectDetectionTrainData,
    addRasaStoryFile,
    addRasaSlotFile,
    addRasaFormFile,
    addRasaActionFile,
    addImageClassificationTrainData,
    updateAnomalyDatasets,
    updateRasaDatasets,
    updateRasaIntentFile,
    updateRasaResponseFile,
    updateRasaRuleFile,
    updateRasaStoryFile,
    updateRasaEntityFile,
    updateRasaSlotFile,
    updateRasaFormFile,
    updateRasaActionFile,
    updateLogClustering,
    updateTimeSeriesPredict,
    updateLogClusteringTrainData,
    updateTimeSeriesPredictTrainData,
    updateClassificationDataset,
    updateObjectDetectionDataset,
    updateClassificationTrainData,
    updateImageClassificationDataset,
    updateImageClassificationTrainData,
    updateObjectDetectionTrainData,
    labelingData,
    deleteAnomalyDatasets,
    deleteAnomalyTrainData,
    deleteRasaDatasets,
    deleteRasaIntentFile,
    deleteRasaResponseFile,
    deleteRasaRuleFile,
    deleteRasaStoryFile,
    deleteRasaEntityFile,
    deleteRasaSlotFile,
    deleteRasaFormFile,
    deleteRasaActionFile,
    deleteTimeSeriesPredict,
    deleteLogClustering,
    deleteLogClusteringTrainData,
    deleteTimeSeriesPredictTrainData,
    deleteClassificationDataset,
    deleteClassificationTrainData,
    deleteImageClassificationDataset,
    deleteImageClassificationTrainData,
    deleteObjectDetectionDataset,
    deleteObjectDetectionTrainData,
    generateYoloDataset
  }
};

export default useMlopsManageApi;