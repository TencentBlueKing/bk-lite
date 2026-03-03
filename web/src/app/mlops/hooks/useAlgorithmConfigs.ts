/**
 * 动态算法配置 Hook
 * 从后端 API 获取算法配置
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import useAlgorithmConfigApi from '@/app/mlops/api/algorithmConfig';
import type { 
  AlgorithmConfigEntity, 
  AlgorithmConfigListItem,
  AlgorithmType,
} from '@/app/mlops/types/algorithmConfig';
import type { AlgorithmConfig } from '@/app/mlops/types/task';

interface UseAlgorithmConfigsResult {
  // 算法配置映射 { algorithmName: AlgorithmConfig }
  algorithmConfigs: Record<string, AlgorithmConfig>;
  // 场景描述映射 { algorithmName: description }
  algorithmScenarios: Record<string, string>;
  // 算法选项列表 [{ value, label }]
  algorithmOptions: Array<{ value: string; label: string }>;
  // 加载状态
  loading: boolean;
  // 错误信息
  error: string | null;
  // 刷新数据
  refresh: () => Promise<void>;
}

/**
 * 获取指定算法类型的动态配置
 * @param algorithmType 算法类型
 */
export const useAlgorithmConfigs = (
  algorithmType: AlgorithmType
): UseAlgorithmConfigsResult => {
  const { getAlgorithmConfigsByType } = useAlgorithmConfigApi();

  const [configs, setConfigs] = useState<AlgorithmConfigEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 从 API 数据转换为组件使用的格式
  const transformedData = useMemo(() => {
    const algorithmConfigs: Record<string, AlgorithmConfig> = {};
    const algorithmScenarios: Record<string, string> = {};
    const algorithmOptions: Array<{ value: string; label: string }> = [];

    for (const config of configs) {
      // form_config 已经是 AlgorithmConfig 格式
      algorithmConfigs[config.name] = config.form_config as unknown as AlgorithmConfig;
      algorithmScenarios[config.name] = config.scenario_description;
      algorithmOptions.push({
        value: config.name,
        label: config.display_name,
      });
    }

    return { algorithmConfigs, algorithmScenarios, algorithmOptions };
  }, [configs]);

  // 加载数据
  const loadConfigs = useCallback(async () => {
    if (!algorithmType) return;

    setLoading(true);
    setError(null);
    
    try {
      const data = await getAlgorithmConfigsByType(algorithmType);
      
      if (data && data.length > 0) {
        setConfigs(data);
      } else {
        setConfigs([]);
      }
    } catch (err) {
      console.error('Failed to load algorithm configs:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [algorithmType]);

  // 初始加载
  useEffect(() => {
    loadConfigs();
  }, [loadConfigs]);

  return {
    ...transformedData,
    loading,
    error,
    refresh: loadConfigs,
  };
};

/**
 * 获取所有算法类型的配置（用于管理页面）
 */
export const useAllAlgorithmConfigs = () => {
  const { getAlgorithmConfigList } = useAlgorithmConfigApi();

  const [configs, setConfigs] = useState<AlgorithmConfigListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });

  const loadConfigs = useCallback(async (params?: {
    algorithm_type?: AlgorithmType;
    page?: number;
    page_size?: number;
  }) => {
    setLoading(true);
    setError(null);

    try {
      const data = await getAlgorithmConfigList({
        algorithm_type: params?.algorithm_type,
        page: params?.page || pagination.current,
        page_size: params?.page_size || pagination.pageSize,
      });

      setConfigs(data.items);
      setPagination(prev => ({
        ...prev,
        total: data.count,
        current: params?.page || prev.current,
      }));
    } catch (err) {
      console.error('Failed to load algorithm configs:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.current, pagination.pageSize]);

  useEffect(() => {
    loadConfigs();
  }, []);

  return {
    configs,
    loading,
    error,
    pagination,
    setPagination,
    refresh: loadConfigs,
  };
};

export default useAlgorithmConfigs;
