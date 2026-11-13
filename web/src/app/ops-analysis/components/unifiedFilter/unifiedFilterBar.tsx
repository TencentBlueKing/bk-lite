'use client';

import React, { useState, useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore } from 'react';
import { Input, InputNumber, Button, ConfigProvider } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import TimeSelector from '@/components/time-selector';
import DateRangeSelector from '@/app/ops-analysis/components/dateRangeSelector';
import GroupTreeSelect from '@/components/group-tree-select';
import { convertGroupTreeToTreeSelectData } from '@/utils/index';
import { normalizeUnifiedFilterInputMode } from '@/app/ops-analysis/utils/widgetDataTransform';
import { ParamInputControl } from '@/app/ops-analysis/components/paramInputControl';
import { useFilterOptionLabelStore } from '@/app/ops-analysis/context/filterTemplate';
import { createFilterOptionLabelStore } from '@/app/ops-analysis/context/filterOptionLabelStore';
import { mapOptionLabels } from '@/app/ops-analysis/utils/filterTemplate';
import { normalizeInputConfig, toSingleOrganizationValue } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import { isMultipleSelectInputConfig } from '@/app/ops-analysis/utils/stringParamMultipleMigrate';
import type {
  UnifiedFilterDefinition,
  FilterValue,
  TimeRangeValue,
} from '@/app/ops-analysis/types/dashBoard';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import {
  areFilterValuesEqual,
  isDynamicOptionFilter,
  reconcileOptionBackedFilterValue,
} from '@/app/ops-analysis/utils/optionBackedFilterValue';
import { useDebouncedOptionsQueryValues } from '@/app/ops-analysis/hooks/useDebouncedOptionsQueryValues';
import {
  dynamicQueryParamsOf,
  readOptionsQueryUpstream,
  resolveOptionsQueryParams,
  stableStringify,
  valueOfFoundOptionsQueryUpstream,
} from '@/app/ops-analysis/utils/optionsQueryParamRefs';
import { isFreeTextOptionsFilter } from '@/app/ops-analysis/utils/optionsQueryTextDebounce';
import { ROOM_FILTER_PASSTHROUGH } from '@/app/ops-analysis/utils/room3DScreenFilter';
import { resolveBuiltinCanvasFilterAppliedValue } from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';
import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import { useTranslation } from '@/utils/i18n';
import { useShareMode } from '@/app/ops-analysis/context/shareMode';
import {
  useShareOrganization,
  useShareOrganizationSeed,
} from '@/app/ops-analysis/context/shareOrganization';
import { getUnifiedFilterTimeSelectorDefaultValue } from '@/app/ops-analysis/utils/filterValue';
import {
  buildResetFilterValues,
  fillMissingOrganizationFilterValues,
  isOrganizationFilterDefinition,
} from '@/app/ops-analysis/utils/unifiedFilterState';

interface UnifiedFilterBarProps {
  definitions: UnifiedFilterDefinition[];
  values: Record<string, FilterValue>;
  onChange?: (values: Record<string, FilterValue>) => void;
  onSearch?: (values: Record<string, FilterValue>) => void;
  onReset?: (values: Record<string, FilterValue>) => void;
  /** 选项第一次回来时把校正写入已应用初值，不触发搜索。 */
  onApplyInitial?: (values: Record<string, FilterValue>) => void;
  prefixContent?: React.ReactNode;
  containerClassName?: string;
  appearance?: 'default' | 'embedded';
  popupZIndex?: number;
}

const EMPTY_LABEL_STORE = createFilterOptionLabelStore();

const toFilterValue = (value: number | number[] | undefined): FilterValue => {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
};

const toNumberFilterValue = (value: number | string | null): FilterValue => {
  if (value === null || value === undefined || value === '') return null;
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

/** 机房自动搜索回写后，已提交字段都在，多出来的键（例如补上的组织）也算同一次回声。 */
const coversPublishedValues = (
  published: Record<string, FilterValue>,
  incoming: Record<string, FilterValue>,
) => Object.keys(published).every((key) => areFilterValuesEqual(published[key], incoming[key]));

const UnifiedFilterBar: React.FC<UnifiedFilterBarProps> = ({
  definitions,
  values,
  onChange,
  onSearch,
  onReset,
  onApplyInitial,
  prefixContent,
  containerClassName,
  appearance = 'default',
  popupZIndex,
}) => {
  const { t } = useTranslation();
  const labelStore = useFilterOptionLabelStore();
  const labelSnapshot = useSyncExternalStore(
    labelStore?.subscribe ?? EMPTY_LABEL_STORE.subscribe,
    labelStore?.getSnapshot ?? EMPTY_LABEL_STORE.getSnapshot,
    labelStore?.getServerSnapshot ?? EMPTY_LABEL_STORE.getServerSnapshot,
  );
  const shareMode = useShareMode();
  const shareOrganization = useShareOrganization();
  const organizationSeed = useShareOrganizationSeed();
  const [localValues, setLocalValues] =
    useState<Record<string, FilterValue>>(values);
  const localValuesRef = useRef(localValues);
  const definitionsRef = useRef(definitions);
  const valuesRef = useRef(values);
  const onApplyInitialRef = useRef(onApplyInitial);
  const onSearchRef = useRef(onSearch);
  const onChangeRef = useRef(onChange);
  const roomPublishEchoRef = useRef<Record<string, FilterValue> | null>(null);
  const optionsByFilterRef = useRef<Map<string, InputOption[]>>(new Map());
  const initialReconciledRef = useRef(new Set<string>());
  const initialAppliedRef = useRef<Record<string, FilterValue> | null>(null);
  localValuesRef.current = localValues;
  definitionsRef.current = definitions;
  valuesRef.current = values;
  onApplyInitialRef.current = onApplyInitial;
  onSearchRef.current = onSearch;
  onChangeRef.current = onChange;
  const organizationTreeData = useMemo(
    () => (shareMode
      ? convertGroupTreeToTreeSelectData(shareOrganization?.groupTree ?? [])
      : undefined),
    [shareMode, shareOrganization],
  );

  const enabledDefinitions = definitions
    .filter((d) => d.enabled)
    .sort((a, b) => a.order - b.order);
  const optionsQueryTextIds = enabledDefinitions
    .filter(isFreeTextOptionsFilter)
    .map((definition) => definition.id);
  // 输入框继续显示 localValues。下游选项查询只读防抖后的文本/数字。
  const optionsQueryValues = useDebouncedOptionsQueryValues(
    localValues,
    optionsQueryTextIds,
  );
  const coveredFilterKey = enabledDefinitions
    .filter(isDynamicOptionFilter)
    .map((definition) => definition.id)
    .join('\0');
  const enabledIdsKey = enabledDefinitions.map((definition) => definition.id).join('\0');
  const enabledIdsKeyRef = useRef(enabledIdsKey);
  if (enabledIdsKeyRef.current !== enabledIdsKey) {
    enabledIdsKeyRef.current = enabledIdsKey;
    initialReconciledRef.current = new Set();
    initialAppliedRef.current = null;
  }

  useEffect(() => {
    const published = roomPublishEchoRef.current;
    if (published && coversPublishedValues(published, values)) {
      roomPublishEchoRef.current = null;
      setLocalValues((prev) => {
        let changed = false;
        const next = { ...prev };
        Object.entries(values).forEach(([key, value]) => {
          if (Object.prototype.hasOwnProperty.call(published, key)) return;
          if (areFilterValuesEqual(next[key], value)) return;
          next[key] = value;
          changed = true;
        });
        return changed ? next : prev;
      });
      return;
    }
    roomPublishEchoRef.current = null;
    setLocalValues(values);
  }, [values]);

  useLayoutEffect(() => {
    if (!labelStore) return undefined;
    return labelStore.claim(coveredFilterKey ? coveredFilterKey.split('\0') : []);
  }, [coveredFilterKey, labelStore]);

  if (enabledDefinitions.length === 0 && !prefixContent) {
    return null;
  }

  const isEmbedded = appearance === 'embedded';
  const popupTheme = popupZIndex
    ? {
      token: {
        zIndexPopupBase: popupZIndex,
      },
    }
    : undefined;

  const handleLocalValueChange = (filterId: string, value: FilterValue) => {
    setLocalValues((prev) => ({
      ...prev,
      [filterId]: value,
    }));
  };

  const handleTimeRangeChange = (
    filterId: string,
    range: number[],
    originValue: number | null,
  ) => {
    if (range.length === 2) {
      const timeRangeValue: TimeRangeValue = {
        start: dayjs(range[0]).toISOString(),
        end: dayjs(range[1]).toISOString(),
        selectValue: originValue ?? 0,
      };
      handleLocalValueChange(filterId, timeRangeValue);
      return;
    }

    handleLocalValueChange(filterId, null);
  };

  const publishValues = (
    next: Record<string, FilterValue>,
    notify: 'search' | 'reset' = 'search',
  ) => {
    localValuesRef.current = next;
    setLocalValues(next);
    if (notify === 'reset' && onReset) {
      onReset(next);
      return;
    }
    (onSearch || onChange)?.(next);
  };

  const writeDraftValues = (next: Record<string, FilterValue>) => {
    localValuesRef.current = next;
    setLocalValues(next);
  };

  const handleSearch = () => {
    publishValues(localValuesRef.current);
  };

  const reconcileFilterOptions = (filterId: string, options: InputOption[]) => {
    optionsByFilterRef.current.set(filterId, options);
    const definition = definitionsRef.current.find((item) => item.id === filterId);
    if (!definition) return;
    const current = localValuesRef.current[filterId];
    const roomValue = resolveBuiltinCanvasFilterAppliedValue(definition, current, options);
    if (roomValue !== ROOM_FILTER_PASSTHROUGH) {
      if (roomValue === undefined) return;
      writeDraftValues({
        ...localValuesRef.current,
        [filterId]: roomValue,
      });
      const committed = {
        ...valuesRef.current,
        [filterId]: roomValue,
      };
      if (areFilterValuesEqual(valuesRef.current[filterId], roomValue)) return;
      const notify = onSearchRef.current || onChangeRef.current;
      if (!notify) return;
      roomPublishEchoRef.current = committed;
      notify(committed);
      return;
    }
    const nextValue = reconcileOptionBackedFilterValue(definition, current, options);
    const firstResolve = !initialReconciledRef.current.has(filterId);
    if (firstResolve) initialReconciledRef.current.add(filterId);
    if (nextValue === undefined) return;
    if (firstResolve) {
      const base = { ...(initialAppliedRef.current ?? valuesRef.current) };
      if (!areFilterValuesEqual(base[filterId], nextValue)) {
        base[filterId] = nextValue;
        initialAppliedRef.current = base;
        onApplyInitialRef.current?.(base);
      } else {
        initialAppliedRef.current = base;
      }
    }
    writeDraftValues({
      ...localValuesRef.current,
      [filterId]: nextValue,
    });
  };

  const handleReset = () => {
    const resetValues = fillMissingOrganizationFilterValues(
      enabledDefinitions,
      buildResetFilterValues(enabledDefinitions),
      organizationSeed,
    );
    enabledDefinitions.forEach((definition) => {
      const options = optionsByFilterRef.current.get(definition.id);
      if (!options) {
        if (isDynamicOptionFilter(definition)) {
          resetValues[definition.id] = null;
        }
        return;
      }
      const roomValue = resolveBuiltinCanvasFilterAppliedValue(definition, null, options);
      if (roomValue !== ROOM_FILTER_PASSTHROUGH) {
        resetValues[definition.id] = roomValue === undefined ? null : roomValue;
        return;
      }
      const retained = reconcileOptionBackedFilterValue(definition, null, options);
      resetValues[definition.id] = retained === undefined ? null : retained;
    });
    publishValues(resetValues, 'reset');
  };

  const getFilterInputConfig = (
    definition: UnifiedFilterDefinition,
  ): InputControlConfig | undefined => {
    const normalized = normalizeInputConfig(definition);
    const inputMode = normalizeUnifiedFilterInputMode(definition.inputMode);
    if (normalized) {
      if (normalized.control === 'organization') {
        return normalized;
      }
      if (inputMode === 'select' || inputMode === 'radio') {
        if (normalized.control === 'input') {
          return {
            control: inputMode,
            optionsSource: {
              type: 'static',
              staticItems: [],
            },
          };
        }
        if (normalized.control === 'select' || normalized.control === 'radio') {
          if (normalized.control === inputMode) {
            return normalized;
          }
          return { ...normalized, control: inputMode };
        }
        return normalized;
      }
      return normalized;
    }
    if (inputMode === 'select' || inputMode === 'radio') {
      return {
        control: inputMode,
        optionsSource: {
          type: 'static',
          staticItems: [],
        },
      };
    }
    return undefined;
  };

  const renderFilterControl = (definition: UnifiedFilterDefinition) => {
    const value = localValues[definition.id];

    switch (definition.type) {
      case 'timeRange': {
        const defaultValue = getUnifiedFilterTimeSelectorDefaultValue(value);

        return (
          <TimeSelector
            key={`${definition.id}-${JSON.stringify(defaultValue)}`}
            onlyTimeSelect
            defaultValue={defaultValue}
            onChange={(range, originValue) =>
              handleTimeRangeChange(definition.id, range, originValue)
            }
          />
        );
      }
      case 'dateRange':
        return (
          <DateRangeSelector
            value={value as DateRangeValue | null | undefined}
            onChange={(nextValue) =>
              handleLocalValueChange(definition.id, nextValue)
            }
          />
        );

      case 'number':
        return (
          <InputNumber
            value={typeof value === 'number' ? value : null}
            onChange={(nextValue) =>
              handleLocalValueChange(definition.id, toNumberFilterValue(nextValue))
            }
            placeholder={definition.name}
            className="min-w-40"
          />
        );

      case 'string':
      default: {
        if (isOrganizationFilterDefinition(definition)) {
          return (
            <GroupTreeSelect
              treeData={organizationTreeData}
              value={toSingleOrganizationValue(value)}
              onChange={(val) => handleLocalValueChange(definition.id, toFilterValue(val))}
              multiple={false}
              mode="ownership"
              allowClear={false}
              placeholder=" "
              style={{ minWidth: 180 }}
            />
          );
        }

        const inputConfig = getFilterInputConfig(definition);
        const isMultiple = isMultipleSelectInputConfig(inputConfig);
        const queryResolution = resolveOptionsQueryParams(
          dynamicQueryParamsOf(inputConfig),
          (ref) => {
            const upstream = readOptionsQueryUpstream(
              ref,
              enabledDefinitions,
              (id) => optionsQueryValues[id],
            );
            if (upstream.found === false) return undefined;
            return valueOfFoundOptionsQueryUpstream(upstream);
          },
        );
        const optionsQuerySignature = stableStringify({
          blocked: queryResolution.blocked,
          blockReason: queryResolution.blockReason ?? null,
          params: queryResolution.params,
        });

        const fallbackInput = (
          <Input
            value={(typeof value === 'string' || typeof value === 'number') ? String(value) : ''}
            onChange={(e) =>
              handleLocalValueChange(definition.id, e.target.value)
            }
            placeholder={definition.name}
            allowClear
            style={{ minWidth: 160 }}
          />
        );

        const controlValue = Array.isArray(value)
          ? value
          : (typeof value === 'string' || typeof value === 'number')
            ? value
            : undefined;

        return (
          <ParamInputControl
            inputConfig={inputConfig}
            fallback={fallbackInput}
            value={controlValue}
            resolvedQueryParams={queryResolution.params}
            optionsBlocked={queryResolution.blocked}
            optionsBlockReason={queryResolution.blockReason}
            optionsQuerySignature={optionsQuerySignature}
            optionsNotifyKey={
              isDynamicOptionFilter(definition)
                ? String(labelSnapshot.revisions[definition.id] ?? 0)
                : undefined
            }
            onOptionsFailed={() => {
              if (isDynamicOptionFilter(definition)) {
                labelStore?.publish(definition.id, {});
              }
            }}
            onOptionsResolved={(options) => {
              if (isDynamicOptionFilter(definition)) {
                labelStore?.publish(definition.id, mapOptionLabels(options));
              }
              reconcileFilterOptions(definition.id, options);
            }}
            onChange={(nextValue) => {
              if (isMultiple) {
                if (Array.isArray(nextValue)) {
                  handleLocalValueChange(definition.id, nextValue);
                  return;
                }
                if (typeof nextValue === 'string' || typeof nextValue === 'number') {
                  handleLocalValueChange(definition.id, [nextValue]);
                  return;
                }
                handleLocalValueChange(definition.id, null);
                return;
              }
              handleLocalValueChange(definition.id, nextValue ?? null);
            }}
            placeholder={definition.name}
            allowClear
            style={{ minWidth: 220 }}
          />
        );
      }
    }
  };

  return (
    <ConfigProvider
      getPopupContainer={() => document.body}
      theme={popupTheme}
    >
      <div
        data-ops-analysis-filter-bar=""
        className={
          isEmbedded
            ? `border-b border-(--color-border-2) bg-transparent px-4 py-3 ${containerClassName ?? ''}`
            : `rounded-lg border border-(--color-border-2) bg-(--color-bg-1) px-3 py-2 ${containerClassName ?? 'mx-0'}`
        }
      >
        <div
          className={`flex flex-wrap items-center ${isEmbedded ? 'gap-x-4 gap-y-2' : 'gap-x-3 gap-y-2.5'}`}
        >
          {prefixContent}
          {enabledDefinitions.map((definition) => (
            <div
              key={definition.id}
              className={
                isEmbedded
                  ? 'flex items-center gap-2'
                  : 'flex items-center gap-2 px-1 py-1'
              }
            >
              <span className="text-xs font-medium tracking-[0.02em] text-(--color-text-2) whitespace-nowrap">
                {definition.name}:
              </span>
              {renderFilterControl(definition)}
            </div>
          ))}
          <div
            className="flex shrink-0 items-center gap-2 whitespace-nowrap"
            data-export-hidden="true"
          >
            <Button
              type="primary"
              size="middle"
              icon={<SearchOutlined />}
              onClick={handleSearch}
              className="rounded-lg!"
            >
              {t('common.search')}
            </Button>
            <Button
              size="middle"
              icon={<ReloadOutlined />}
              onClick={handleReset}
              className="rounded-lg!"
            >
              {t('common.reset')}
            </Button>
          </div>
        </div>
      </div>
    </ConfigProvider>
  );
};

export default UnifiedFilterBar;
