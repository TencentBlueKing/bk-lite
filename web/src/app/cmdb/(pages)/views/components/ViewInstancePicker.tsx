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
import { viewAllowsMultiSelect } from '../viewEligibility';
import { readViewRecent } from '../viewMemory';
import {
  mergeRackRoomGroups,
  rackGroupsToSelectOptions,
  type RackPickerRoomGroup,
} from '../rackPickerGroups';

const SEARCH_PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;
const SELECT_SCROLL_LOAD_OFFSET = 24;

export interface ViewInstancePickerProps {
  viewType: ViewType;
  mode?: RackRoomMode;
  eligibleModelIds: string[];
  focus: ViewFocus | null;
  focuses?: ViewFocus[];
  onFocusChange: (focus: ViewFocus | null) => void;
  onFocusesChange?: (focuses: ViewFocus[]) => void;
}

interface InstanceOption {
  value: string;
  label: string;
  model_id: string;
  inst_name: string;
  room_name?: string;
}

const ViewInstancePicker: React.FC<ViewInstancePickerProps> = ({
  viewType,
  mode,
  eligibleModelIds,
  focus,
  focuses,
  onFocusChange,
  onFocusesChange,
}) => {
  const { t } = useTranslation();
  const { searchInstances, getRacksGroupedByRoom } = useInstanceApi();
  const common = useCommon();
  const { userId } = useUserInfoContext();
  const modelList: ModelItem[] = common?.modelList ?? [];
  const allowMultiple = viewAllowsMultiSelect(viewType, mode);
  const groupByRoom = viewType === 'rack-room' && mode === 'rack';
  const selectedFocuses = useMemo(() => {
    if (focuses?.length) return focuses;
    return focus ? [focus] : [];
  }, [focuses, focus]);

  const [selectedModelId, setSelectedModelId] = useState<string | undefined>(
    focus?.model_id
  );
  const [instanceOptions, setInstanceOptions] = useState<InstanceOption[]>([]);
  const [roomGroups, setRoomGroups] = useState<RackPickerRoomGroup[]>([]);
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
  const getRacksGroupedByRoomRef = useRef(getRacksGroupedByRoom);
  getRacksGroupedByRoomRef.current = getRacksGroupedByRoom;
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
      grouped,
    }: {
      modelId: string;
      keyword: string;
      page: number;
      append: boolean;
      grouped: boolean;
    }) => {
      if (!modelId) {
        setInstanceOptions([]);
        setRoomGroups([]);
        setInstancePage(1);
        setInstanceTotal(0);
        loadedQueryRef.current = null;
        return;
      }
      const seq = ++searchSeqRef.current;
      setLoading(true);
      try {
        if (grouped) {
          const data = await getRacksGroupedByRoomRef.current({
            search: keyword,
            page,
            page_size: SEARCH_PAGE_SIZE,
          });
          if (seq !== searchSeqRef.current) return;
          const nextGroups: RackPickerRoomGroup[] = (
            Array.isArray(data?.groups) ? data.groups : []
          ).map((group: {
            room_uuid?: string | null;
            room_name?: string;
            racks?: { inst_uuid?: string; inst_name?: string; model_id?: string }[];
          }) => ({
            room_uuid: group.room_uuid || null,
            room_name: group.room_name || '',
            racks: (Array.isArray(group.racks) ? group.racks : [])
              .map((rack) => {
                const instUuid = resolveCmdbInstUuid(rack.inst_uuid);
                if (!instUuid) return null;
                return {
                  inst_uuid: instUuid,
                  inst_name: rack.inst_name || instUuid,
                  model_id: rack.model_id || modelId,
                };
              })
              .filter((item): item is NonNullable<typeof item> => item != null),
          }));
          setRoomGroups((prev) => mergeRackRoomGroups(prev, nextGroups, append));
          const nextOptions: InstanceOption[] = nextGroups.flatMap((group) =>
            group.racks.map((rack) => ({
              value: rack.inst_uuid,
              label: rack.inst_name,
              model_id: rack.model_id || modelId,
              inst_name: rack.inst_name,
              room_name: group.room_name,
            }))
          );
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
            || (append ? prev : nextGroups.length)
          );
          if (!append) {
            loadedQueryRef.current = queryKey(modelId, keyword);
          }
          return;
        }

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
        setRoomGroups([]);
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
          setRoomGroups([]);
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
    setRoomGroups([]);
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
      grouped: groupByRoom,
    });
  }, [dropdownOpen, selectedModelId, instanceKeyword, fetchInstances, groupByRoom]);

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

  const resolveFocusName = (instId: string) => {
    const fromSearch = instanceOptions.find((item) => item.value === instId);
    const fromRecent = recentItems.find((item) => item.inst_uuid === instId);
    const fromSelected = selectedFocuses.find((item) => item.inst_uuid === instId);
    return fromSearch?.inst_name
      || fromRecent?.inst_name
      || fromSelected?.inst_name;
  };

  const emitFocuses = (next: ViewFocus[]) => {
    if (onFocusesChange) {
      onFocusesChange(next);
      return;
    }
    onFocusChange(next[0] ?? null);
  };

  const handleModelChange = (modelId: string) => {
    resetInstanceList();
    setSelectedModelId(modelId);
    emitFocuses([]);
  };

  const handleInstanceSearch = (value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const keyword = value.trim();
    debounceRef.current = setTimeout(() => {
      setInstanceKeyword(keyword);
      // Force a fresh page-1 fetch for the new keyword even if options linger.
      loadedQueryRef.current = null;
      setInstanceOptions([]);
      setRoomGroups([]);
      setInstancePage(1);
      setInstanceTotal(0);
    }, SEARCH_DEBOUNCE_MS);
  };

  const handleInstancePopupScroll = (event: React.UIEvent<HTMLDivElement>) => {
    if (!selectedModelId || loading) return;
    const loadedCount = groupByRoom ? roomGroups.length : instanceOptions.length;
    const hasMore = loadedCount < instanceTotal;
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
      grouped: groupByRoom,
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
        setRoomGroups([]);
        setInstancePage(1);
        setInstanceTotal(0);
      }
    }
  };

  const handleInstanceChange = (value: string | string[] | undefined) => {
    if (!selectedModelId) {
      emitFocuses([]);
      return;
    }
    const instIds = Array.isArray(value)
      ? value.filter(Boolean)
      : (value ? [value] : []);
    if (!instIds.length) {
      emitFocuses([]);
      return;
    }
    emitFocuses(instIds.map((instId) => buildFocus(
      selectedModelId,
      instId,
      resolveFocusName(instId),
    )));
  };

  const selectOptions = useMemo(() => {
    if (groupByRoom) {
      return rackGroupsToSelectOptions({
        recent: recentItems,
        groups: roomGroups,
        selected: selectedFocuses.filter((item) => item.model_id === selectedModelId),
        keyword: instanceKeyword,
        recentLabel: t('ViewsHub.recent'),
        unassociatedLabel: t('ViewsHub.unassociatedRoom'),
        rackWithRoom: t('ViewsHub.rackWithRoom'),
      });
    }

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

    selectedFocuses
      .filter((item) =>
        item.model_id === selectedModelId
        && !recentIds.has(item.inst_uuid)
        && !instanceOptions.some((opt) => opt.value === item.inst_uuid)
      )
      .forEach((item) => {
        searchOpts.unshift({
          label: item.inst_name || item.inst_uuid,
          value: item.inst_uuid,
        });
      });

    groups.push({
      label: t('ViewsHub.selectInstance'),
      options: searchOpts,
    });

    return groups;
  }, [
    groupByRoom,
    roomGroups,
    recentItems,
    instanceOptions,
    selectedFocuses,
    selectedModelId,
    instanceKeyword,
    t,
  ]);

  const matchingFocuses = selectedFocuses.filter(
    (item) => item.model_id === selectedModelId
  );
  const selectValue = allowMultiple
    ? matchingFocuses.map((item) => item.inst_uuid)
    : matchingFocuses[0]?.inst_uuid;

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
        key={allowMultiple ? 'multi' : 'single'}
        className={allowMultiple ? 'min-w-[280px] w-[420px]' : 'min-w-[240px] w-[320px]'}
        placeholder={
          groupByRoom
            ? t('ViewsHub.selectInstanceGrouped')
            : allowMultiple
              ? t('ViewsHub.selectInstanceMultiple')
              : t('ViewsHub.selectInstance')
        }
        mode={allowMultiple ? 'multiple' : undefined}
        maxTagCount={allowMultiple ? 'responsive' : undefined}
        value={selectValue}
        options={selectOptions}
        loading={loading}
        showSearch
        filterOption={false}
        optionLabelProp={groupByRoom ? 'selectedLabel' : 'label'}
        onSearch={handleInstanceSearch}
        onPopupScroll={handleInstancePopupScroll}
        onOpenChange={handleDropdownVisibleChange}
        allowClear
        disabled={!selectedModelId}
        onChange={(value) => handleInstanceChange(value as string | string[] | undefined)}
        notFoundContent={loading ? null : undefined}
      />
    </div>
  );
};

export default ViewInstancePicker;
