import useApiClient from "@/utils/request";

interface LabelData {
  timestamp: number | string;
  value: number;
  label?: number;
}

interface AnomalyDetectionReason {
  model_name: string;
  model_version: string;
  algorithm: string;
  data: LabelData[];
  anomaly_threshold: number;
}

const usePlayroundApi = () => {
  const {
    get,
    post,
    patch,
    del
  } = useApiClient();

  // 获取分类列表
  const getCategoryList = async () => {
    return await get(`/playground/category/`);
  };

  // 获取异常检测能力发布列表
  const getAnomalyServingsList = async () => {
    return await get(`/mlops/anomaly_detection_servings/`);
  };

  // 获取时序预测能力列表
  const getTimeSeriesPredictServingsList = async () => {
    return await get(`/mlops/timeseries_predict_servings/`);
  };

  // 获取日志聚类能力列表
  const getLogClusteringServingsList = async () => {
    return await get(`/mlops/log_clustering_servings/`);
  };

  // 获取分类任务能力列表
  const getClassificationServingsList = async () => {
    return await get(`/mlops/classification_servings`);
  };
  
  // 获取能力发布详情
  const getServingsDetail = async (id: string) => {
    return await get(`/mlops/anomaly_detection_servings/${id}/`)
  };

  // 获取时序预测能力详情
  const getTimeseriesServingDetail = async (id: string) => {
    return await get(`/mlops/timeseries_predict_servings/${id}/`);
  };

  // 获取日志聚类能力详情
  const getLogClusteringServingDetail = async (id: string) => {
    return await get(`/mlops/log_clustering_servings/${id}/`);
  };

  // 获取分类任务能力详情
  const getClassificationServingDetail = async (id: string) => {
    return await get(`/mlops/classification_servings/${id}/`);
  };

  // 查询单个类别
  const getCategoryDetail = async (id: number) => {
    return await get(`/playground/category/${id}`);
  };

  // 查询能力演示列表
  const getCapabilityList = async () => {
    return await get(`/playground/capability/`);
  };

  // 查询单个能力演示
  const getCapabilityDetail = async (id: string) => {
    return await get(`/playground/capability/${id}`);
  };

  // 查询所有的样本文件列表
  const getAllSampleFileList = async ({
    name = '',
    page = 1,
    page_size = -1,
  }: {
    name?: string,
    page?: number,
    page_size?: number
  }) => {
    return await get(`/playground/example/?name=${name}&page=${page}&page_size=${page_size}`);
  };
  
  // 查询指定能力体验下的样本文件
  const getSampleFileOfCapability = async (capability: string) => {
    return await get(`/playground/example/?capability=${capability}`);
  };

  // 获取指定样本文件详情
  const getSampleFileDetail = async (id: number) => {
    return await get(`/playground/example/${id}`);
  };

  // 创建分类
  const createCategory = async (params: {
    name: string,
    description: string,
    parant: number
  }) => {
    return await post(`/playground/category/`, params);
  };

  // 修改类别
  const updateCategory = async (id: number, params: {
    name: string,
    description: string,
    parent: number
  }) => {
    return await patch(`/playground/category/${id}/`, params)
  };

  // 创建能力演示
  const createCapability = async (params: {
    name: string,
    description: string,
    config: object,
    is_active: boolean,
    url: string
  }) => {
    return await post(`/playground/capability/`, params);
  };

  // 编辑能力演示
  const updateCapability = async (id: number, params: {
    name: string,
    description: string,
    config: object,
    is_active: boolean,
    url: string,
  }) => {
    return await patch(`/playground/capability/${id}/`, params);
  };

  // 创建样本文件
  const createSampleFile = async (params: {
    name: string;
    capability: number;
    train_data: LabelData[],
    is_active: boolean;
  }) => {
    return await post(`playground/example/`, params)
  };

  // 编辑样本文件
  const updateSampleFile = async (id: number, params: {
    is_active: boolean
  }) => {
    return await patch(`/playground/example/${id}`, params)
  };

  // 异常检测推理
  const anomalyDetectionReason = async (params: AnomalyDetectionReason) => {
    return await post(`/mlops/anomaly_detection_servings/predict/`, params);
  };

  // 删除类别
  const deleteCategory = async (id: number) => {
    return await del(`/playground/category/${id}/`);
  };

  // 删除演示能力
  const deleteCapability = async (id: number) => {
    return await del(`/playground/capability/${id}`);
  };

  // 删除指定样本文件
  const deleteSampleFile = async (id: number) => {
    return await del(`/playground/example/${id}`);
  };

  return {
    getCategoryList,
    getAnomalyServingsList,
    getTimeSeriesPredictServingsList,
    getLogClusteringServingsList,
    getCategoryDetail,
    getCapabilityList,
    getCapabilityDetail,
    getAllSampleFileList,
    getSampleFileDetail,
    getServingsDetail,
    getSampleFileOfCapability,
    getClassificationServingsList,
    getTimeseriesServingDetail,
    getLogClusteringServingDetail,
    getClassificationServingDetail,
    createCategory,
    createCapability,
    createSampleFile,
    updateCategory,
    updateCapability,
    updateSampleFile,
    anomalyDetectionReason,
    deleteCategory,
    deleteCapability,
    deleteSampleFile
  }

};

export default usePlayroundApi;