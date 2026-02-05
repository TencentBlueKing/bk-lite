/**
 * 动态算法配置 Hook
 * 从后端 API 获取算法配置，支持回退到静态配置
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import useAlgorithmConfigApi from '@/app/mlops/api/algorithmConfig';
import type { 
  AlgorithmConfigEntity, 
  AlgorithmConfigListItem,
  AlgorithmType,
  // FormConfig
} from '@/app/mlops/types/algorithmConfig';
import type { AlgorithmConfig } from '@/app/mlops/types/task';

// 静态配置导入（作为回退）
import { ANOMALY_ALGORITHM_CONFIGS, ANOMALY_ALGORITHM_SCENARIOS } from '@/app/mlops/constants/algorithms/anomaly-detection';
import { TIMESERIES_ALGORITHM_CONFIGS, TIMESERIES_ALGORITHM_SCENARIOS } from '@/app/mlops/constants/algorithms/timeseries-predict';
import { LOG_CLUSTERING_ALGORITHM_CONFIGS, LOG_CLUSTERING_ALGORITHM_SCENARIOS } from '@/app/mlops/constants/algorithms/log-clustering';
import { CLASSIFICATION_ALGORITHM_CONFIGS, CLASSIFICATION_ALGORITHM_SCENARIOS } from '@/app/mlops/constants/algorithms/classification';
import { IMAGE_CLASSIFICATION_ALGORITHM_CONFIGS, IMAGE_CLASSIFICATION_ALGORITHM_SCENARIOS } from '@/app/mlops/constants/algorithms/image-classification';
import { OBJECT_DETECTION_ALGORITHM_CONFIGS, OBJECT_DETECTION_ALGORITHM_SCENARIOS } from '@/app/mlops/constants/algorithms/object-detection';

// 静态配置映射
const STATIC_CONFIGS: Record<AlgorithmType, {
  configs: Record<string, AlgorithmConfig>;
  scenarios: Record<string, string>;
}> = {
  anomaly_detection: {
    configs: ANOMALY_ALGORITHM_CONFIGS,
    scenarios: ANOMALY_ALGORITHM_SCENARIOS,
  },
  timeseries_predict: {
    configs: TIMESERIES_ALGORITHM_CONFIGS,
    scenarios: TIMESERIES_ALGORITHM_SCENARIOS,
  },
  log_clustering: {
    configs: LOG_CLUSTERING_ALGORITHM_CONFIGS,
    scenarios: LOG_CLUSTERING_ALGORITHM_SCENARIOS,
  },
  classification: {
    configs: CLASSIFICATION_ALGORITHM_CONFIGS,
    scenarios: CLASSIFICATION_ALGORITHM_SCENARIOS,
  },
  image_classification: {
    configs: IMAGE_CLASSIFICATION_ALGORITHM_CONFIGS,
    scenarios: IMAGE_CLASSIFICATION_ALGORITHM_SCENARIOS,
  },
  object_detection: {
    configs: OBJECT_DETECTION_ALGORITHM_CONFIGS,
    scenarios: OBJECT_DETECTION_ALGORITHM_SCENARIOS,
  },
};

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
  // 是否使用的是静态配置
  isUsingFallback: boolean;
  // 刷新数据
  refresh: () => Promise<void>;
}

/**
 * 获取指定算法类型的动态配置
 * @param algorithmType 算法类型
 * @param useFallback 是否在 API 失败时使用静态配置（默认 true）
 */
export const useAlgorithmConfigs = (
  algorithmType: AlgorithmType,
  useFallback: boolean = true
): UseAlgorithmConfigsResult => {
  const { getAlgorithmConfigsByType } = useAlgorithmConfigApi();

  const [configs, setConfigs] = useState<AlgorithmConfigEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUsingFallback, setIsUsingFallback] = useState(false);

  // 从 API 数据转换为组件使用的格式
  const transformedData = useMemo(() => {
    if (isUsingFallback) {
      const staticData = STATIC_CONFIGS[algorithmType];
      return {
        algorithmConfigs: staticData?.configs || {},
        algorithmScenarios: staticData?.scenarios || {},
        algorithmOptions: Object.keys(staticData?.configs || {}).map(key => ({
          value: key,
          label: key,  // 使用 key 作为 label，与动态配置保持一致
        })),
      };
    }

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
  }, [configs, isUsingFallback, algorithmType]);

  // 加载数据
  const loadConfigs = useCallback(async () => {
    if (!algorithmType) return;

    setLoading(true);
    setError(null);
    
    try {
      const data = await getAlgorithmConfigsByType(algorithmType);
      
      if (data && data.length > 0) {
        setConfigs(data);
        setIsUsingFallback(false);
      } else if (useFallback) {
        // API 返回空数据，使用静态配置
        console.warn(`No algorithm configs found for ${algorithmType}, using fallback`);
        setIsUsingFallback(true);
      } else {
        setConfigs([]);
      }
    } catch (err) {
      console.error('Failed to load algorithm configs:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
      
      if (useFallback) {
        console.warn(`Failed to load configs for ${algorithmType}, using fallback`);
        setIsUsingFallback(true);
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [algorithmType, useFallback]);

  // 初始加载
  useEffect(() => {
    loadConfigs();
  }, [loadConfigs]);

  return {
    ...transformedData,
    loading,
    error,
    isUsingFallback,
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
