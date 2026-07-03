import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Form } from 'antd';
import type { FormInstance } from 'antd';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import {
  filterNetworkTopologyModelOptions,
  getNetworkTopologyModelIds,
} from '@/app/ops-analysis/utils/networkTopologyModels';

const NETWORK_INSTANCE_PAGE_SIZE = 100;
const SELECT_SCROLL_LOAD_OFFSET = 24;

export interface NetworkSelectOption {
  label: string;
  value: string;
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

export const mapNetworkInstanceOptions = (
  instances: any[],
): NetworkSelectOption[] =>
  (instances || []).map((instance: any) => {
    const instanceId = instance._id || instance.id;
    return {
      label: String(instance.inst_name || instance.name || instanceId),
      value: String(instanceId),
    };
  });

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
  const [instanceOptions, setInstanceOptions] = useState<NetworkSelectOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [instancesLoading, setInstancesLoading] = useState(false);
  const [instancePage, setInstancePage] = useState(1);
  const [instanceTotal, setInstanceTotal] = useState(0);
  const [instanceKeyword, setInstanceKeyword] = useState('');
  const instanceRequestIdRef = useRef(0);
  const instanceSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sceneModelId = Form.useWatch(['networkStatusTopology', 'modelId'], form);

  const resetInstanceOptions = useCallback(() => {
    setInstanceOptions([]);
    setInstancePage(1);
    setInstanceTotal(0);
    setInstanceKeyword('');
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
    // API hooks return fresh function references; this load is driven by panel/component state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, modelOptions.length, open]);

  const fetchNetworkInstances = async ({
    page,
    keyword,
    append,
  }: {
    page: number;
    keyword: string;
    append: boolean;
  }) => {
    if (!sceneModelId) return;

    const requestId = instanceRequestIdRef.current + 1;
    instanceRequestIdRef.current = requestId;
    setInstancesLoading(true);

    try {
      const trimmedKeyword = keyword.trim();
      const instanceRes = await searchInstances({
        model_id: sceneModelId,
        query_list: trimmedKeyword
          ? [{ field: 'inst_name', type: 'str*', value: trimmedKeyword }]
          : [],
        page,
        page_size: NETWORK_INSTANCE_PAGE_SIZE,
        order: '',
        role: '',
        case_sensitive: false,
      });

      if (requestId !== instanceRequestIdRef.current) return;

      const nextOptions = mapNetworkInstanceOptions(instanceRes?.insts || []);
      setInstanceOptions((previous) =>
        append ? mergeNetworkSelectOptions(previous, nextOptions) : nextOptions,
      );
      setInstancePage(page);
      setInstanceTotal(Number(instanceRes?.count) || nextOptions.length);
    } catch (error) {
      console.error('获取网络拓扑实例失败:', error);
      if (requestId === instanceRequestIdRef.current) {
        setInstanceOptions((previous) => (append ? previous : []));
        setInstanceTotal((previous) => (append ? previous : 0));
      }
    } finally {
      if (requestId === instanceRequestIdRef.current) {
        setInstancesLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!open || !enabled || !sceneModelId) {
      resetInstanceOptions();
      return;
    }

    resetInstanceOptions();
    void fetchNetworkInstances({ page: 1, keyword: '', append: false });
    // API hooks return fresh function references; this load is driven by model/panel state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    enabled,
    open,
    sceneModelId,
  ]);

  useEffect(() => {
    return () => {
      if (instanceSearchTimerRef.current) {
        clearTimeout(instanceSearchTimerRef.current);
      }
    };
  }, []);

  const handleInstanceSearch = (keyword: string) => {
    setInstanceKeyword(keyword);
    if (instanceSearchTimerRef.current) {
      clearTimeout(instanceSearchTimerRef.current);
    }
    instanceSearchTimerRef.current = setTimeout(() => {
      resetInstanceOptions();
      void fetchNetworkInstances({ page: 1, keyword, append: false });
    }, 300);
  };

  const handleInstancePopupScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const hasMore = instanceOptions.length < instanceTotal;
    const isNearBottom =
      target.scrollTop + target.offsetHeight >=
      target.scrollHeight - SELECT_SCROLL_LOAD_OFFSET;

    if (!hasMore || instancesLoading || !isNearBottom) {
      return;
    }

    void fetchNetworkInstances({
      page: instancePage + 1,
      keyword: instanceKeyword,
      append: true,
    });
  };

  const handleModelChange = () => {
    form.setFieldValue(['networkStatusTopology', 'instId'], undefined);
    resetInstanceOptions();
  };

  return {
    sceneModelId,
    modelOptions,
    instanceOptions,
    modelsLoading,
    instancesLoading,
    resetInstanceOptions,
    handleModelChange,
    handleInstanceSearch,
    handleInstancePopupScroll,
  };
};
