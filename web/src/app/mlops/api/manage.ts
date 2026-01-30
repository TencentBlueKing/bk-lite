import useApiClient from "@/utils/request";
import { DATASET_MAP, TRAINDATA_MAP } from "@/app/mlops/constants";
import type { 
  DatasetType,
  BaseTrainDataUpdateParams,
  AnomalyTrainDataUpdateParams,
  ObjectDetectionTrainDataUpdateParams,
  ImageClassificationTrainDataUpdateParams
} from "../types";

const useMlopsManageApi = () => {
  const {
    get,
    post,
    put,
    del,
    patch
  } = useApiClient();

  // 获取数据集列表
  const getDatasetsList = async ({
    key,
    page = 1,
    page_size = -1
  }: {
    key: DatasetType,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/mlops/${DATASET_MAP[key]}/?page=${page}&page_size=${page_size}`);
  };

  // 获取指定数据集详情
  const getOneDatasetInfo = async (id: number, key: DatasetType) => {
    return await get(`/mlops/${DATASET_MAP[key]}/${id}/`);
  };

  // 查询指定数据集下的样本列表
  const getTrainDataByDataset = async (
    {
      key,
      name = '',
      dataset,
      page = 1,
      page_size = -1
    }: {
      key: DatasetType,
      name?: string;
      dataset?: string | number;
      page?: number;
      page_size?: number;
    }
  ) => {
    return await get(`/mlops/${TRAINDATA_MAP[key]}/?dataset=${dataset}&name=${name}&page=${page}&page_size=${page_size}`)
  };

  // 获取指定样本的详情
  const getTrainDataInfo = async (id: number | string, key: DatasetType,include_train_data?: boolean, include_metadata?: boolean) => {
    return await get(`/mlops/${TRAINDATA_MAP[key]}/${id}?include_train_data=${include_train_data}&include_metadata=${include_metadata}`);
  };

  // 下载图片分类训练数据压缩包
  // const getImageTrainDataZip = async (id: number | string) => {
  //   return await get(`/mlops/image_classification_train_data/${id}/download`);
  // };
  
  // 新增数据集
  const addDataset = async (key: DatasetType, params: {
    name: string;
    description: string;
  }) => {
    return await post(`/mlops/${DATASET_MAP[key]}/`, params);
  };


  // 新增异常数据检测集样本
  const addAnomalyTrainData = async (params: FormData) => {
    return await post(`/mlops/anomaly_detection_train_data`, params, {
      headers: {
        "Content-Type": 'multipart/form-data'
      }
    });
  };

  // 新增日志聚类数据集样本文件
  const addLogClusteringTrainData = async (params: FormData) => {
    return await post(`/mlops/log_clustering_train_data`, params, {
      headers: {
        "Content-Type": 'multipart/form-data'
      }
    });
  };

  // 新增时序预测样本文件
  const addTimeSeriesPredictTrainData = async (params: FormData) => {
    return await post(`/mlops/timeseries_predict_train_data`, params, {
      headers: {
        "Content-Type": 'multipart/form-data'
      }
    });
  };

  // 新增分类任务样本文件
  const addClassificationTrainData = async (params: FormData) => {
    return await post(`/mlops/classification_train_data`, params, {
      headers: {
        "Content-Type": 'multipart/form-data'
      }
    });
  };

  // 新增图片分类任务样本文件
  const addImageClassificationTrainData = async (params: FormData) => {
    return await post(`/mlops/image_classification_train_data`, params, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  };

  // 新增目标检测任务样本文件
  const addObjectDetectionTrainData = async (params: FormData) => {
    return await post(`/mlops/object_detection_train_data`, params, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  };

  // 更新数据集
  const updateDataset = async (id: number, key: DatasetType, params: {
    name: string;
    description: string;
  }) => {
    return await put(`/mlops/${DATASET_MAP[key]}/${id}`, params);
  };

  // 更新异常检测数据集样本文件
  const updateAnomalyTrainDataFile = async (
    id: string, 
    params: AnomalyTrainDataUpdateParams | FormData
  ) => {
    return await patch(`/mlops/anomaly_detection_train_data/${id}/`, params, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
  };

  // 更新日志聚类数据集样本文件
  const updateLogClusteringTrainData = async (
    id: string, 
    params: BaseTrainDataUpdateParams & { train_data?: unknown[] }
  ) => {
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
    params: ImageClassificationTrainDataUpdateParams | FormData
  ) => {
    return await patch(`/mlops/image_classification_train_data/${id}`, params,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
  };

  // 更新目标检测任务数据集样本文件
  const updateObjectDetectionTrainData = async (
    id: string, 
    params: ObjectDetectionTrainDataUpdateParams | FormData
  ) => {
    return await patch(`/mlops/object_detection_train_data/${id}`, params,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
  };

  // 删除数据集
  const deleteDataset = async (id: number, key: DatasetType) => {
    return await del(`/mlops/${DATASET_MAP[key]}/${id}`);
  };

  // 删除训练样本文件
  const deleteTrainDataFile = async (id: number, key: DatasetType) => {
    return await del(`/mlops/${TRAINDATA_MAP[key]}/${id}/`);
  };

  return {
    getDatasetsList,
    getOneDatasetInfo,
    getTrainDataByDataset,
    getTrainDataInfo,

    addDataset,

    addAnomalyTrainData,
    addLogClusteringTrainData,
    addTimeSeriesPredictTrainData,
    addClassificationTrainData,
    addObjectDetectionTrainData,
    addImageClassificationTrainData,

    updateDataset,

    updateLogClusteringTrainData,
    updateTimeSeriesPredictTrainData,
    updateClassificationTrainData,
    updateImageClassificationTrainData,
    updateObjectDetectionTrainData,
    updateAnomalyTrainDataFile,

    deleteDataset,
    deleteTrainDataFile,
  }
};

export default useMlopsManageApi;