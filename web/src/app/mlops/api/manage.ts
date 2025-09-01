import useApiClient from "@/utils/request";
import { TrainDataParams } from '@/app/mlops/types/manage';

interface TrainDataBrochure {
  dataset: number;
  name: string;
  train_data: TrainDataParams[];
  metadata: object;
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

  // 获取指定异常检测数据集详情
  const getOneAnomalyDataset = async (id: number) => {
    return await get(`/mlops/anomaly_detection_datasets/${id}/`);
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

  // 获取指定异常检测样本的详情
  const getAnomalyTrainDataInfo = async (id: number | string, include_train_data?: boolean, include_metadata?: boolean) => {
    return await get(`/mlops/anomaly_detection_train_data/${id}?include_train_data=${include_train_data}&include_metadata=${include_metadata}`);
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

  // 新增异常数据检测集样本
  const addAnomalyTrainData = async (params: TrainDataBrochure) => {
    return await post(`/mlops/anomaly_detection_train_data`, params);
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

  // 更新Rasa意图文件
  const updateRasaIntentFile = async (id: number, params: {
    name: string;
    example: string[];
  }) => {
    return await put(`/mlops/rasa_intent/${id}`, params);
  };

  // 更新Rasa响应文件
  const updateRasaResponseFile = async (id: number, params: {
    name: string;
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

  // 删除异常检测数据集
  const deleteAnomalyDatasets = async (id: number) => {
    return await del(`/mlops/anomaly_detection_datasets/${id}`);
  };

  // 删除Rasa数据集
  const deleteRasaDatasets = async (id: number) => {
    return await del(`/mlops/rasa_datasets/${id}`);
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

  // 删除训练数据
  const deleteAnomalyTrainData = async (id: number) => {
    return await del(`/mlops/anomaly_detection_train_data/${id}/`);
  };

  return {
    getAnomalyDatasetsList,
    getRasaDatasetsList,
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
    addAnomalyDatasets,
    addRasaDatasets,
    addRasaIntentFile,
    addRasaResponseFile,
    addRasaRuleFile,
    addRasaEntityFile,
    addAnomalyTrainData,
    addRasaStoryFile,
    addRasaSlotFile,
    addRasaFormFile,
    updateAnomalyDatasets,
    updateRasaDatasets,
    updateRasaIntentFile,
    updateRasaResponseFile,
    updateRasaRuleFile,
    updateRasaStoryFile,
    updateRasaEntityFile,
    updateRasaSlotFile,
    updateRasaFormFile,
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
    deleteRasaFormFile
  }
};

export default useMlopsManageApi;