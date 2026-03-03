/**
 * 算法配置管理 API
 */
import useApiClient from "@/utils/request";
import type {
  AlgorithmConfigEntity,
  AlgorithmConfigListItem,
  AlgorithmConfigParams,
  AlgorithmConfigQueryParams,
  AlgorithmType,
} from "../types/algorithmConfig";

const useAlgorithmConfigApi = () => {
  const { get, post, patch, del } = useApiClient();

  // 获取算法配置列表
  const getAlgorithmConfigList = async (
    params?: AlgorithmConfigQueryParams
  ): Promise<{ items: AlgorithmConfigListItem[]; count: number }> => {
    const algorithmType = params?.algorithm_type;
    if (!algorithmType) {
      return { items: [], count: 0 };
    }
    return await get(`/mlops/${algorithmType}_algorithm_configs/`, { params });
  };

  // 获取单个算法配置详情
  const getAlgorithmConfigById = async (algorithmType: AlgorithmType, id: number): Promise<AlgorithmConfigEntity> => {
    return await get(`/mlops/${algorithmType}_algorithm_configs/${id}/`);
  };

  // 根据算法类型获取启用的算法配置列表
  const getAlgorithmConfigsByType = async (
    algorithmType: AlgorithmType
  ): Promise<AlgorithmConfigEntity[]> => {
    return await get(`/mlops/${algorithmType}_algorithm_configs/by_type/`);
  };

  // 根据算法类型和名称获取镜像
  const getAlgorithmImage = async (
    algorithmType: AlgorithmType,
    name: string
  ): Promise<{ image: string }> => {
    return await get(`/mlops/${algorithmType}_algorithm_configs/get_image/?name=${name}`);
  };

  // 创建算法配置
  const createAlgorithmConfig = async (
    algorithmType: AlgorithmType,
    params: AlgorithmConfigParams
  ): Promise<AlgorithmConfigEntity> => {
    return await post(`/mlops/${algorithmType}_algorithm_configs/`, params);
  };

  // 更新算法配置（部分更新）
  const updateAlgorithmConfig = async (
    algorithmType: AlgorithmType,
    id: number,
    params: Partial<AlgorithmConfigParams>
  ): Promise<AlgorithmConfigEntity> => {
    return await patch(`/mlops/${algorithmType}_algorithm_configs/${id}/`, params);
  };

  // 删除算法配置
  const deleteAlgorithmConfig = async (algorithmType: AlgorithmType, id: number): Promise<void> => {
    return await del(`/mlops/${algorithmType}_algorithm_configs/${id}/`);
  };

  return {
    getAlgorithmConfigList,
    getAlgorithmConfigById,
    getAlgorithmConfigsByType,
    getAlgorithmImage,
    createAlgorithmConfig,
    updateAlgorithmConfig,
    deleteAlgorithmConfig,
  };
};

export default useAlgorithmConfigApi;
