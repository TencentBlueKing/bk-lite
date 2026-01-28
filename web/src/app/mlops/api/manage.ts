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

  // 获取Rasa实体数
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

  // 删除训练样本文件
  const deleteTrainDataFile = async (id: number, key: DatasetType) => {
    return await del(`/mlops/${TRAINDATA_MAP[key]}/${id}/`);
  };

  return {
    getDatasetsList,
    getOneDatasetInfo,
    getTrainDataByDataset,
    getTrainDataInfo,
    // rasa
    getRasaIntentFileList,
    getRasaResponseFileList,
    getRasaRuleFileList,
    getRasaStoryFileList,
    getRasaEntityList,
    getRasaEntityCount,
    getRasaSlotList,
    getRasaFormList,
    getRasaActionList,

    addDataset,
    // rasa
    addRasaIntentFile,
    addRasaResponseFile,
    addRasaRuleFile,
    addRasaEntityFile,
    addRasaStoryFile,
    addRasaSlotFile,
    addRasaFormFile,
    addRasaActionFile,

    addAnomalyTrainData,
    addLogClusteringTrainData,
    addTimeSeriesPredictTrainData,
    addClassificationTrainData,
    addObjectDetectionTrainData,
    addImageClassificationTrainData,

    updateDataset,
    // rasa
    updateRasaIntentFile,
    updateRasaResponseFile,
    updateRasaRuleFile,
    updateRasaStoryFile,
    updateRasaEntityFile,
    updateRasaSlotFile,
    updateRasaFormFile,
    updateRasaActionFile,

    updateLogClusteringTrainData,
    updateTimeSeriesPredictTrainData,
    updateClassificationTrainData,
    updateImageClassificationTrainData,
    updateObjectDetectionTrainData,
    updateAnomalyTrainDataFile,

    deleteDataset,
    deleteTrainDataFile,
    // rasa
    deleteRasaIntentFile,
    deleteRasaResponseFile,
    deleteRasaRuleFile,
    deleteRasaStoryFile,
    deleteRasaEntityFile,
    deleteRasaSlotFile,
    deleteRasaFormFile,
    deleteRasaActionFile,
  }
};

export default useMlopsManageApi;