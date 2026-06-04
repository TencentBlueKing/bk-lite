'use client';

import React, { useState, useEffect } from 'react';
import { Input, Button, ConfigProvider, Select } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import TimeSelector from '@/components/time-selector';
import type {
  UnifiedFilterDefinition,
  FilterValue,
  TimeRangeValue,
} from '@/app/ops-analysis/types/dashBoard';
import { useTranslation } from '@/utils/i18n';

interface UnifiedFilterBarProps {
  definitions: UnifiedFilterDefinition[];
  values: Record<string, FilterValue>;
  onChange?: (values: Record<string, FilterValue>) => void;
  onSearch?: (values: Record<string, FilterValue>) => void;
  onReset?: (values: Record<string, FilterValue>) => void;
  prefixContent?: React.ReactNode;
  containerClassName?: string;
  appearance?: 'default' | 'embedded';
  popupZIndex?: number;
}

const UnifiedFilterBar: React.FC<UnifiedFilterBarProps> = ({
  definitions,
  values,
  onChange,
  onSearch,
  onReset,
  prefixContent,
  containerClassName,
  appearance = 'default',
  popupZIndex,
}) => {
  const { t } = useTranslation();
  const [localValues, setLocalValues] =
    useState<Record<string, FilterValue>>(values);

  const enabledDefinitions = definitions
    .filter((d) => d.enabled)
    .sort((a, b) => a.order - b.order);

  useEffect(() => {
    setLocalValues(values);
  }, [values]);

  if (enabledDefinitions.length === 0 && !prefixContent) {
    return null;
  }

  const isEmbedded = appearance === 'embedded';

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

  const getTimeSelectorDefaultValue = (
    value: FilterValue,
  ): {
    selectValue: number;
    rangePickerVaule: [dayjs.Dayjs, dayjs.Dayjs] | null;
  } => {
    const timeValue = value as TimeRangeValue | null | undefined;
    if (!timeValue || !timeValue.start || !timeValue.end) {
      return { selectValue: 15, rangePickerVaule: null };
    }

    const selectVal = timeValue.selectValue ?? 0;
    if (selectVal > 0) {
      return { selectValue: selectVal, rangePickerVaule: null };
    }

    return {
      selectValue: 0,
      rangePickerVaule: [dayjs(timeValue.start), dayjs(timeValue.end)],
    };
  };

  const handleSearch = () => {
    (onSearch || onChange)?.(localValues);
  };

  const handleReset = () => {
    const emptyValues: Record<string, FilterValue> = {};
    enabledDefinitions.forEach((def) => {
      emptyValues[def.id] = def.defaultValue ?? null;
    });
    setLocalValues(emptyValues);

    if (onReset) {
      onReset(emptyValues);
      return;
    }

    (onSearch || onChange)?.(emptyValues);
  };

  const renderFilterControl = (definition: UnifiedFilterDefinition) => {
    const value = localValues[definition.id];

    switch (definition.type) {
      case 'timeRange': {
        const defaultValue = getTimeSelectorDefaultValue(value);

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

      case 'string':
      default:
        if (definition.inputMode === 'select' && definition.options?.length) {
          return (
            <Select
              value={(value as string) || undefined}
              onChange={(val) =>
                handleLocalValueChange(definition.id, val ?? null)
              }
              placeholder={definition.name}
              allowClear
              style={{ minWidth: 160 }}
              options={definition.options}
            />
          );
        }

        return (
          <Input
            value={(value as string) || ''}
            onChange={(e) =>
              handleLocalValueChange(definition.id, e.target.value)
            }
            placeholder={definition.name}
            allowClear
            style={{ minWidth: 160 }}
          />
        );
    }
  };

  return (
    <ConfigProvider
      getPopupContainer={() => document.body}
      theme={
        popupZIndex
          ? {
              token: {
                zIndexPopupBase: popupZIndex,
              },
            }
          : undefined
      }
    >
      <div
        className={
          isEmbedded
            ? `border-b border-(--color-border-2) bg-transparent px-4 py-3 ${containerClassName ?? ''}`
            : `rounded-lg border border-(--color-border-2) bg-(--color-bg-1) px-3 py-2 ${containerClassName ?? 'mx-2.5 mt-1 mb-2'}`
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
