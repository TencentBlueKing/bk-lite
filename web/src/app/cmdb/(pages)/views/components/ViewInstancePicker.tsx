'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import type { ModelItem } from '@/app/cmdb/types/assetManage';
import type { RackRoomMode, ViewFocus, ViewType } from '../viewTypes';
import { readViewRecent } from '../viewMemory';

const SEARCH_PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

export interface ViewInstancePickerProps {
  viewType: ViewType;
  mode?: RackRoomMode;
  eligibleModelIds: string[];
  focus: ViewFocus | null;
  onFocusChange: (focus: ViewFocus | null) => void;
}

interface InstanceOption {
  value: string;
  label: string;
  model_id: string;
  inst_name: string;
}

const ViewInstancePicker: React.FC<ViewInstancePickerProps> = ({
  viewType,
  mode,
  eligibleModelIds,
  focus,
  onFocusChange,
}) => {
  const { t } = useTranslation();
  const { searchInstances } = useInstanceApi();
  const common = useCommon();
  const { userId } = useUserInfoContext();
  const modelList: ModelItem[] = common?.modelList ?? [];

  const [selectedModelId, setSelectedModelId] = useState<string | undefined>(
    focus?.model_id
  );
  const [instanceOptions, setInstanceOptions] = useState<InstanceOption[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSeqRef = useRef(0);
  // useInstanceApi() returns a new searchInstances each render — keep a ref so
  // fetch effects do not re-fire into an instance/search request storm.
  const searchInstancesRef = useRef(searchInstances);
  searchInstancesRef.current = searchInstances;

  const modelOptions = useMemo(
    () =>
      eligibleModelIds.map((modelId) => {
        const model = modelList.find((item) => item.model_id === modelId);
        return {
          value: modelId,
          label: model?.model_name || modelId,
        };
      }),
    [eligibleModelIds, modelList]
  );

  const recentItems = useMemo(() => {
    if (typeof window === 'undefined' || !userId || !selectedModelId) return [];
    const recent = readViewRecent(window.localStorage, userId, viewType);
    return recent.filter((item) => {
      if (item.model_id !== selectedModelId) return false;
      if (viewType === 'rack-room' && mode && item.mode && item.mode !== mode) {
        return false;
      }
      return true;
    });
    // Re-read when focus changes so newly pushed recent appears.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, viewType, selectedModelId, mode, focus?.inst_id, focus?.model_id]);

  useEffect(() => {
    if (focus?.model_id && eligibleModelIds.includes(focus.model_id)) {
      setSelectedModelId(focus.model_id);
      return;
    }
    if (selectedModelId && eligibleModelIds.includes(selectedModelId)) {
      return;
    }
    setSelectedModelId(eligibleModelIds[0]);
  }, [focus?.model_id, eligibleModelIds, selectedModelId]);

  const resolveModelMeta = useCallback(
    (modelId: string) => {
      const model = modelList.find((item) => item.model_id === modelId);
      return {
        model_name: model?.model_name,
        icn: model?.icn,
      };
    },
    [modelList]
  );

  const fetchInstances = useCallback(async (modelId: string, keyword: string) => {
    if (!modelId) {
      setInstanceOptions([]);
      return;
    }
    const seq = ++searchSeqRef.current;
    setLoading(true);
    try {
      const data = await searchInstancesRef.current({
        model_id: modelId,
        query_list: keyword
          ? [{ field: 'inst_name', type: 'str*', value: keyword }]
          : [],
        page: 1,
        page_size: SEARCH_PAGE_SIZE,
        order: '',
        role: '',
      });
      if (seq !== searchSeqRef.current) return;
      const insts = Array.isArray(data?.insts) ? data.insts : [];
      setInstanceOptions(
        insts.map((item: { _id?: string | number; inst_name?: string }) => ({
          value: String(item._id),
          label: item.inst_name || String(item._id),
          model_id: modelId,
          inst_name: item.inst_name || String(item._id),
        }))
      );
    } catch {
      if (seq !== searchSeqRef.current) return;
      setInstanceOptions([]);
    } finally {
      if (seq === searchSeqRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!selectedModelId) {
      setInstanceOptions([]);
      return;
    }
    void fetchInstances(selectedModelId, '');
  }, [selectedModelId, fetchInstances]);

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    []
  );

  const buildFocus = (
    modelId: string,
    instId: string,
    instName?: string
  ): ViewFocus => {
    const meta = resolveModelMeta(modelId);
    return {
      model_id: modelId,
      inst_id: instId,
      inst_name: instName,
      model_name: meta.model_name,
      icn: meta.icn,
      ...(viewType === 'rack-room' && mode ? { mode } : {}),
    };
  };

  const handleModelChange = (modelId: string) => {
    setSelectedModelId(modelId);
    setInstanceOptions([]);
    onFocusChange(null);
  };

  const handleInstanceSearch = (value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (selectedModelId) {
        void fetchInstances(selectedModelId, value);
      }
    }, SEARCH_DEBOUNCE_MS);
  };

  const handleInstanceChange = (instId: string | undefined) => {
    if (!instId || !selectedModelId) {
      onFocusChange(null);
      return;
    }
    const fromSearch = instanceOptions.find((item) => item.value === instId);
    const fromRecent = recentItems.find((item) => item.inst_id === instId);
    onFocusChange(
      buildFocus(
        selectedModelId,
        instId,
        fromSearch?.inst_name
          || fromRecent?.inst_name
          || (focus?.inst_id === instId ? focus.inst_name : undefined)
      )
    );
  };

  const selectOptions = useMemo(() => {
    const groups: {
      label: string;
      options: { label: string; value: string }[];
    }[] = [];

    if (recentItems.length > 0) {
      groups.push({
        label: t('ViewsHub.recent'),
        options: recentItems.map((item) => ({
          label: item.inst_name || item.inst_id,
          value: item.inst_id,
        })),
      });
    }

    const recentIds = new Set(recentItems.map((item) => item.inst_id));
    const searchOpts = instanceOptions
      .filter((item) => !recentIds.has(item.value))
      .map((item) => ({
        label: item.label,
        value: item.value,
      }));

    if (
      focus
      && focus.model_id === selectedModelId
      && !recentIds.has(focus.inst_id)
      && !instanceOptions.some((item) => item.value === focus.inst_id)
    ) {
      searchOpts.unshift({
        label: focus.inst_name || focus.inst_id,
        value: focus.inst_id,
      });
    }

    groups.push({
      label: t('ViewsHub.selectInstance'),
      options: searchOpts,
    });

    return groups;
  }, [recentItems, instanceOptions, focus, selectedModelId, t]);

  const selectValue =
    focus && focus.model_id === selectedModelId ? focus.inst_id : undefined;

  return (
    <div className="flex items-center gap-2 flex-wrap min-w-0">
      <Select
        className="w-[180px]"
        placeholder={t('ViewsHub.selectModel')}
        value={selectedModelId}
        options={modelOptions}
        onChange={handleModelChange}
        showSearch
        optionFilterProp="label"
        disabled={eligibleModelIds.length === 0}
      />
      <Select
        className="min-w-[240px] w-[320px]"
        placeholder={t('ViewsHub.selectInstance')}
        value={selectValue}
        options={selectOptions}
        loading={loading}
        showSearch
        filterOption={false}
        onSearch={handleInstanceSearch}
        allowClear
        disabled={!selectedModelId}
        onChange={(value) => handleInstanceChange(value)}
        notFoundContent={loading ? null : undefined}
      />
    </div>
  );
};

export default ViewInstancePicker;
