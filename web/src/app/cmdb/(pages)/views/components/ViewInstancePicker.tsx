'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import type { ModelItem } from '@/app/cmdb/types/assetManage';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import type { RackRoomMode, ViewFocus, ViewType } from '../viewTypes';
import { readViewRecent } from '../viewMemory';

const SEARCH_PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;
const SELECT_SCROLL_LOAD_OFFSET = 24;

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
  const [instancePage, setInstancePage] = useState(1);
  const [instanceTotal, setInstanceTotal] = useState(0);
  const [instanceKeyword, setInstanceKeyword] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSeqRef = useRef(0);
  // useInstanceApi() returns a new searchInstances each render — keep a ref so
  // fetch effects do not re-fire into an instance/search request storm.
  const searchInstancesRef = useRef(searchInstances);
  searchInstancesRef.current = searchInstances;
  /** Last model+keyword pair that completed a non-append page-1 load. */
  const loadedQueryRef = useRef<string | null>(null);

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
     
  }, [userId, viewType, selectedModelId, mode, focus?.inst_uuid, focus?.model_id]);

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

  const queryKey = (modelId: string, keyword: string) =>
    `${modelId}::${keyword}`;

  const fetchInstances = useCallback(
    async ({
      modelId,
      keyword,
      page,
      append,
    }: {
      modelId: string;
      keyword: string;
      page: number;
      append: boolean;
    }) => {
      if (!modelId) {
        setInstanceOptions([]);
        setInstancePage(1);
        setInstanceTotal(0);
        loadedQueryRef.current = null;
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
          page,
          page_size: SEARCH_PAGE_SIZE,
          order: '',
          role: '',
          case_sensitive: false,
        });
        if (seq !== searchSeqRef.current) return;
        const insts = Array.isArray(data?.insts) ? data.insts : [];
        const nextOptions: InstanceOption[] = insts
          .map((item: { inst_uuid?: string; inst_name?: string }) => {
            const instUuid = resolveCmdbInstUuid(item.inst_uuid);
            if (!instUuid) return null;
            return {
              value: instUuid,
              label: item.inst_name || instUuid,
              model_id: modelId,
              inst_name: item.inst_name || instUuid,
            };
          })
          .filter((item): item is InstanceOption => item != null);
        setInstanceOptions((prev) => {
          if (!append) return nextOptions;
          const seen = new Set(prev.map((item) => item.value));
          return [
            ...prev,
            ...nextOptions.filter((item) => !seen.has(item.value)),
          ];
        });
        setInstancePage(page);
        setInstanceTotal((prev) =>
          Number(data?.count)
          || (append ? prev : nextOptions.length)
        );
        if (!append) {
          loadedQueryRef.current = queryKey(modelId, keyword);
        }
      } catch {
        if (seq !== searchSeqRef.current) return;
        if (!append) {
          setInstanceOptions([]);
          setInstanceTotal(0);
          loadedQueryRef.current = null;
        }
      } finally {
        if (seq === searchSeqRef.current) {
          setLoading(false);
        }
      }
    },
    []
  );

  const resetInstanceList = useCallback(() => {
    setInstanceOptions([]);
    setInstancePage(1);
    setInstanceTotal(0);
    setInstanceKeyword('');
    loadedQueryRef.current = null;
  }, []);

  // Only fetch when the instance dropdown is open — avoid loading large lists
  // just because the model changed while the user is looking at the canvas.
  useEffect(() => {
    if (!dropdownOpen || !selectedModelId) return;
    const key = queryKey(selectedModelId, instanceKeyword);
    if (loadedQueryRef.current === key) return;
    void fetchInstances({
      modelId: selectedModelId,
      keyword: instanceKeyword,
      page: 1,
      append: false,
    });
  }, [dropdownOpen, selectedModelId, instanceKeyword, fetchInstances]);

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
      inst_uuid: instId,
      inst_name: instName,
      model_name: meta.model_name,
      icn: meta.icn,
      ...(viewType === 'rack-room' && mode ? { mode } : {}),
    };
  };

  const handleModelChange = (modelId: string) => {
    resetInstanceList();
    setSelectedModelId(modelId);
    onFocusChange(null);
  };

  const handleInstanceSearch = (value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const keyword = value.trim();
    debounceRef.current = setTimeout(() => {
      setInstanceKeyword(keyword);
      // Force a fresh page-1 fetch for the new keyword even if options linger.
      loadedQueryRef.current = null;
      setInstanceOptions([]);
      setInstancePage(1);
      setInstanceTotal(0);
    }, SEARCH_DEBOUNCE_MS);
  };

  const handleInstancePopupScroll = (event: React.UIEvent<HTMLDivElement>) => {
    if (!selectedModelId || loading) return;
    const hasMore = instanceOptions.length < instanceTotal;
    if (!hasMore) return;
    const target = event.currentTarget;
    const isNearBottom =
      target.scrollTop + target.offsetHeight
      >= target.scrollHeight - SELECT_SCROLL_LOAD_OFFSET;
    if (!isNearBottom) return;
    void fetchInstances({
      modelId: selectedModelId,
      keyword: instanceKeyword,
      page: instancePage + 1,
      append: true,
    });
  };

  const handleDropdownVisibleChange = (open: boolean) => {
    setDropdownOpen(open);
    if (!open) {
      // Drop search filter when closing so the next open starts from page 1
      // of the full list (recent + first page), not a stale keyword filter.
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (instanceKeyword) {
        setInstanceKeyword('');
        loadedQueryRef.current = null;
        setInstanceOptions([]);
        setInstancePage(1);
        setInstanceTotal(0);
      }
    }
  };

  const handleInstanceChange = (instId: string | undefined) => {
    if (!instId || !selectedModelId) {
      onFocusChange(null);
      return;
    }
    const fromSearch = instanceOptions.find((item) => item.value === instId);
    const fromRecent = recentItems.find((item) => item.inst_uuid === instId);
    onFocusChange(
      buildFocus(
        selectedModelId,
        instId,
        fromSearch?.inst_name
          || fromRecent?.inst_name
          || (focus?.inst_uuid === instId ? focus.inst_name : undefined)
      )
    );
  };

  const selectOptions = useMemo(() => {
    const groups: {
      label: string;
      options: { label: string; value: string }[];
    }[] = [];

    if (recentItems.length > 0 && !instanceKeyword) {
      groups.push({
        label: t('ViewsHub.recent'),
        options: recentItems.map((item) => ({
          label: item.inst_name || item.inst_uuid,
          value: item.inst_uuid,
        })),
      });
    }

    const recentIds = new Set(
      instanceKeyword ? [] : recentItems.map((item) => item.inst_uuid)
    );
    const searchOpts = instanceOptions
      .filter((item) => !recentIds.has(item.value))
      .map((item) => ({
        label: item.label,
        value: item.value,
      }));

    if (
      focus
      && focus.model_id === selectedModelId
      && !recentIds.has(focus.inst_uuid)
      && !instanceOptions.some((item) => item.value === focus.inst_uuid)
    ) {
      searchOpts.unshift({
        label: focus.inst_name || focus.inst_uuid,
        value: focus.inst_uuid,
      });
    }

    groups.push({
      label: t('ViewsHub.selectInstance'),
      options: searchOpts,
    });

    return groups;
  }, [
    recentItems,
    instanceOptions,
    focus,
    selectedModelId,
    instanceKeyword,
    t,
  ]);

  const selectValue =
    focus && focus.model_id === selectedModelId ? focus.inst_uuid : undefined;

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
        onPopupScroll={handleInstancePopupScroll}
        onOpenChange={handleDropdownVisibleChange}
        allowClear
        disabled={!selectedModelId}
        onChange={(value) => handleInstanceChange(value)}
        notFoundContent={loading ? null : undefined}
      />
    </div>
  );
};

export default ViewInstancePicker;
