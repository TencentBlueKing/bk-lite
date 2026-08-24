import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Form } from 'antd';
import type { FormInstance } from 'antd';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import {
  filterNetworkTopologyModelOptions,
  getNetworkTopologyModelIds,
} from '@/app/ops-analysis/utils/networkTopologyModels';
import { isValidCmdbInstanceUuid } from '@/app/ops-analysis/utils/cmdbInstanceUuid';
import {
  NETWORK_STATUS_TOPOLOGY_INSTANCE_PAGE_SIZE,
  applyInstancePageSlices,
  collectSettledModelCounts,
  planCrossModelInstancePage,
  sumModelCounts,
  uniqueInstancePageRequests,
} from '../utils/networkStatusTopologyDevicePage';

export interface NetworkSelectOption {
  label: string;
  value: string;
  name?: string;
  modelLabel?: string;
}

interface UseNetworkStatusTopologyConfigInput {
  open: boolean;
  enabled: boolean;
  form: FormInstance;
}

export const mergeNetworkSelectOptions = (
  previous: NetworkSelectOption[],
  next: NetworkSelectOption[],
): NetworkSelectOption[] => {
  const optionMap = new Map(previous.map((item) => [item.value, item]));
  next.forEach((item) => optionMap.set(item.value, item));
  return Array.from(optionMap.values());
};

export const collectSettledInstancePages = (
  results: PromiseSettledResult<{ insts?: unknown[]; count?: number } | null | undefined>[],
): { insts: unknown[]; total: number } => {
  const insts: unknown[] = [];
  let total = 0;
  results.forEach((result) => {
    if (result.status !== 'fulfilled' || !result.value) return;
    insts.push(...(result.value.insts || []));
    total += Number(result.value.count) || 0;
  });
  return { insts, total };
};

export const keepSelectedNetworkOptions = (
  selectedValues: string[],
  cached: NetworkSelectOption[],
  listed: NetworkSelectOption[],
): NetworkSelectOption[] =>
  mergeNetworkSelectOptions(
    cached.filter((item) => selectedValues.includes(item.value)),
    listed,
  );

export const mapNetworkInstanceOptions = (
  instances: unknown[],
  modelLabelById?: Map<string, string>,
): NetworkSelectOption[] => {
  return instances.flatMap((instance) => {
    if (!instance || typeof instance !== 'object') return [];

    const record = instance as Record<string, unknown>;
    if (!isValidCmdbInstanceUuid(record.inst_uuid)) return [];

    const modelId = typeof record.model_id === 'string' ? record.model_id : '';
    const modelLabel = (modelLabelById?.get(modelId) || modelId).trim();
    const name = String(record.inst_name || record.name || record.inst_uuid);
    return [{
      label: modelLabel ? `${name} · ${modelLabel}` : name,
      value: String(record.inst_uuid),
      name,
      modelLabel,
    }];
  });
};

export const useNetworkStatusTopologyConfig = ({
  open,
  enabled,
  form,
}: UseNetworkStatusTopologyConfigInput) => {
  const { getModelList, getModelAssociations } = useModelApi();
  const { searchInstances } = useInstanceApi();
  const [modelOptions, setModelOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const [modelFilter, setModelFilter] = useState<string>();
  const [instanceOptions, setInstanceOptions] = useState<NetworkSelectOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [instancesLoading, setInstancesLoading] = useState(false);
  const [instancePage, setInstancePage] = useState(1);
  const [instancePageSize, setInstancePageSize] = useState(
    NETWORK_STATUS_TOPOLOGY_INSTANCE_PAGE_SIZE,
  );
  const [instanceTotal, setInstanceTotal] = useState(0);
  const [instanceKeyword, setInstanceKeyword] = useState('');
  const instanceRequestIdRef = useRef(0);
  const instanceSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selectedOptionsRef = useRef<NetworkSelectOption[]>([]);
  const modelCountsRef = useRef<ReturnType<typeof collectSettledModelCounts>>([]);
  const countCacheKeyRef = useRef('');
  const instanceKeywordRef = useRef('');
  const instancePageSizeRef = useRef(NETWORK_STATUS_TOPOLOGY_INSTANCE_PAGE_SIZE);
  const modelOptionsRef = useRef(modelOptions);
  modelOptionsRef.current = modelOptions;
  const modelFilterRef = useRef(modelFilter);
  modelFilterRef.current = modelFilter;
  const selectedInstUuids = Form.useWatch(['networkStatusTopology', 'instUuids'], form);
  const selectedValues = Array.isArray(selectedInstUuids) ? selectedInstUuids.map(String) : [];
  const selectedValuesRef = useRef(selectedValues);
  selectedValuesRef.current = selectedValues;

  const resetInstanceOptions = useCallback(() => {
    setInstanceOptions([]);
    setInstancePage(1);
    setInstancePageSize(NETWORK_STATUS_TOPOLOGY_INSTANCE_PAGE_SIZE);
    instancePageSizeRef.current = NETWORK_STATUS_TOPOLOGY_INSTANCE_PAGE_SIZE;
    setInstanceTotal(0);
    setInstanceKeyword('');
    instanceKeywordRef.current = '';
    modelCountsRef.current = [];
    countCacheKeyRef.current = '';
  }, []);

  useEffect(() => {
    if (!open || !enabled || modelOptions.length > 0) {
      return;
    }

    let cancelled = false;
    const fetchModels = async () => {
      try {
        setModelsLoading(true);
        const [models, associations] = await Promise.all([
          getModelList(),
          getModelAssociations('interface'),
        ]);
        if (cancelled) return;
        setModelOptions(
          filterNetworkTopologyModelOptions(
            Array.isArray(models) ? models : [],
            getNetworkTopologyModelIds(
              Array.isArray(associations) ? associations : [],
            ),
          ),
        );
      } catch (error) {
        console.error('获取模型列表失败:', error);
        if (!cancelled) setModelOptions([]);
      } finally {
        if (!cancelled) setModelsLoading(false);
      }
    };

    void fetchModels();
    return () => {
      cancelled = true;
    };
  }, [enabled, modelOptions.length, open]);

  const fetchNetworkInstances = async ({
    page,
    keyword,
    pageSize,
    refreshCounts,
  }: {
    page: number;
    keyword: string;
    pageSize: number;
    refreshCounts: boolean;
  }) => {
    const models = modelFilterRef.current
      ? [modelFilterRef.current]
      : modelOptionsRef.current.map((item) => item.value);
    if (!models.length) return;

    const requestId = instanceRequestIdRef.current + 1;
    instanceRequestIdRef.current = requestId;
    setInstancesLoading(true);
    const modelLabelById = new Map(
      modelOptionsRef.current.map((item) => [item.value, item.label]),
    );
    const trimmedKeyword = keyword.trim();
    const queryList = trimmedKeyword
      ? [{ field: 'inst_name', type: 'str*', value: trimmedKeyword }]
      : [];
    const countCacheKey = `${models.join('|')}::${trimmedKeyword}`;

    try {
      if (
        refreshCounts
        || countCacheKeyRef.current !== countCacheKey
        || modelCountsRef.current.length === 0
      ) {
        const countPages = await Promise.allSettled(
          models.map((modelId) =>
            searchInstances({
              model_id: modelId,
              query_list: queryList,
              page: 1,
              page_size: 1,
              order: '',
              role: '',
              case_sensitive: false,
            }),
          ),
        );
        if (requestId !== instanceRequestIdRef.current) return;
        modelCountsRef.current = collectSettledModelCounts(models, countPages);
        countCacheKeyRef.current = countCacheKey;
        setInstanceTotal(sumModelCounts(modelCountsRef.current));
      }

      const slices = planCrossModelInstancePage(
        modelCountsRef.current,
        page,
        pageSize,
      );
      const requests = uniqueInstancePageRequests(slices);
      const pages = await Promise.allSettled(
        requests.map((request) =>
          searchInstances({
            model_id: request.modelId,
            query_list: queryList,
            page: request.requestPage,
            page_size: request.pageSize,
            order: '',
            role: '',
            case_sensitive: false,
          }),
        ),
      );

      if (requestId !== instanceRequestIdRef.current) return;

      const pagesByKey = new Map<string, unknown[]>();
      requests.forEach((request, index) => {
        const result = pages[index];
        if (result.status !== 'fulfilled' || !result.value) return;
        pagesByKey.set(
          `${request.modelId}:${request.requestPage}`,
          Array.isArray(result.value.insts) ? result.value.insts : [],
        );
      });

      const nextOptions = mapNetworkInstanceOptions(
        applyInstancePageSlices(slices, pagesByKey),
        modelLabelById,
      );
      selectedOptionsRef.current = mergeNetworkSelectOptions(
        selectedOptionsRef.current,
        nextOptions.filter((item) => selectedValuesRef.current.includes(item.value)),
      );
      setInstanceOptions(nextOptions);
      setInstancePage(page);
      setInstancePageSize(pageSize);
    } catch (error) {
      console.error('获取网络拓扑实例失败:', error);
      if (requestId === instanceRequestIdRef.current) {
        setInstanceOptions([]);
        setInstanceTotal(0);
      }
    } finally {
      if (requestId === instanceRequestIdRef.current) {
        setInstancesLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!open || !enabled || modelOptions.length === 0) {
      if (!open || !enabled) resetInstanceOptions();
      return;
    }

    resetInstanceOptions();
    void fetchNetworkInstances({
      page: 1,
      keyword: '',
      pageSize: NETWORK_STATUS_TOPOLOGY_INSTANCE_PAGE_SIZE,
      refreshCounts: true,
    });
  }, [enabled, modelFilter, modelOptions, open, resetInstanceOptions]);

  useEffect(() => {
    if (!open || !enabled || modelOptions.length === 0) return;
    const missing = selectedValuesRef.current.filter(
      (id) => !selectedOptionsRef.current.some((item) => item.value === id),
    );
    if (!missing.length) return;

    let cancelled = false;
    const hydrate = async () => {
      const modelLabelById = new Map(
        modelOptionsRef.current.map((item) => [item.value, item.label]),
      );
      const pages = await Promise.allSettled(
        modelOptionsRef.current.map((item) =>
          searchInstances({
            model_id: item.value,
            query_list: [{ field: 'inst_uuid', type: 'str[]', value: missing }],
            page: 1,
            page_size: Math.max(missing.length, 1),
            order: '',
            role: '',
            case_sensitive: false,
          }),
        ),
      );
      if (cancelled) return;
      const { insts } = collectSettledInstancePages(pages);
      const hydrated = mapNetworkInstanceOptions(insts, modelLabelById);
      selectedOptionsRef.current = mergeNetworkSelectOptions(
        selectedOptionsRef.current,
        hydrated,
      );
    };
    void hydrate();
    return () => {
      cancelled = true;
    };
  }, [enabled, modelOptions, open, selectedValues.join(',')]);

  useEffect(() => {
    return () => {
      if (instanceSearchTimerRef.current) {
        clearTimeout(instanceSearchTimerRef.current);
      }
    };
  }, []);

  const handleInstanceSearch = (keyword: string) => {
    setInstanceKeyword(keyword);
    instanceKeywordRef.current = keyword;
    if (instanceSearchTimerRef.current) {
      clearTimeout(instanceSearchTimerRef.current);
    }
    instanceSearchTimerRef.current = setTimeout(() => {
      setInstancePage(1);
      modelCountsRef.current = [];
      countCacheKeyRef.current = '';
      void fetchNetworkInstances({
        page: 1,
        keyword,
        pageSize: instancePageSizeRef.current,
        refreshCounts: true,
      });
    }, 300);
  };

  const handleInstancePageChange = (page: number, pageSize: number) => {
    const nextPageSize = pageSize || instancePageSizeRef.current;
    const sizeChanged = nextPageSize !== instancePageSizeRef.current;
    instancePageSizeRef.current = nextPageSize;
    setInstancePageSize(nextPageSize);
    void fetchNetworkInstances({
      page: sizeChanged ? 1 : page,
      keyword: instanceKeywordRef.current,
      pageSize: nextPageSize,
      refreshCounts: false,
    });
  };

  const handleModelFilterChange = (value?: string) => {
    setModelFilter(value || undefined);
  };

  return {
    modelFilter,
    modelOptions,
    instanceOptions,
    instancePage,
    instancePageSize,
    instanceTotal,
    instanceKeyword,
    modelsLoading,
    instancesLoading,
    resetInstanceOptions,
    handleModelFilterChange,
    handleInstanceSearch,
    handleInstancePageChange,
  };
};
