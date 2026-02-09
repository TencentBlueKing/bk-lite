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
    return await get('/mlops/algorithm_configs/', { params });
  };

  // 获取单个算法配置详情
  const getAlgorithmConfigById = async (id: number): Promise<AlgorithmConfigEntity> => {
    return await get(`/mlops/algorithm_configs/${id}/`);
  };

  // 根据算法类型获取启用的算法配置列表
  const getAlgorithmConfigsByType = async (
    algorithmType: AlgorithmType
  ): Promise<AlgorithmConfigEntity[]> => {
    return await get(`/mlops/algorithm_configs/by_type/${algorithmType}/`);
  };

  // 根据算法类型和名称获取镜像
  const getAlgorithmImage = async (
    algorithmType: AlgorithmType,
    name: string
  ): Promise<{ image: string }> => {
    return await get(`/mlops/algorithm_configs/get_image/?algorithm_type=${algorithmType}&name=${name}`);
  };

  // 创建算法配置
  const createAlgorithmConfig = async (
    params: AlgorithmConfigParams
  ): Promise<AlgorithmConfigEntity> => {
    return await post('/mlops/algorithm_configs/', params);
  };

  // 更新算法配置（部分更新）
  const updateAlgorithmConfig = async (
    id: number,
    params: Partial<AlgorithmConfigParams>
  ): Promise<AlgorithmConfigEntity> => {
    return await patch(`/mlops/algorithm_configs/${id}/`, params);
  };

  // 删除算法配置
  const deleteAlgorithmConfig = async (id: number): Promise<void> => {
    return await del(`/mlops/algorithm_configs/${id}/`);
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
