'use client';

import React from 'react';
import { Button, Input, Select, Tooltip } from 'antd';
import { CloseOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { FilterItem } from '@/app/monitor/types';
import { sanitizeGroupBy } from '@/app/monitor/utils/metricDimensions';
import { MetricExpressionRow } from './metricExpressionTypes';

interface SelectOption {
  label: string;
  value: string;
}

interface MetricOperandRowProps {
  row: MetricExpressionRow;
  metricOptions: Array<{
    label: string;
    title?: string;
    options: Array<{ label: string; value: string }>;
  }>;
  metricsLoading: boolean;
  groupMethodOptions: SelectOption[];
  conditionMethodOptions: SelectOption[];
  labelOptions: SelectOption[];
  showDimension: boolean;
  dimensionOptions: SelectOption[];
  canDelete: boolean;
  nested?: boolean;
  onMetricChange: (metricName?: string) => void;
  onGroupAlgorithmChange: (value: string) => void;
  onGroupByChange: (value: string[]) => void;
  onFilterChange: (filterIndex: number, patch: Partial<FilterItem>) => void;
  onFilterRemove: (filterIndex: number) => void;
  onFilterAdd: () => void;
  onRemove?: () => void;
}

const MetricOperandRow: React.FC<MetricOperandRowProps> = ({
  row,
  metricOptions,
  metricsLoading,
  groupMethodOptions,
  conditionMethodOptions,
  labelOptions,
  showDimension,
  dimensionOptions,
  canDelete,
  nested = false,
  onMetricChange,
  onGroupAlgorithmChange,
  onGroupByChange,
  onFilterChange,
  onFilterRemove,
  onFilterAdd,
  onRemove
}) => {
  const { t } = useTranslation();
  const translateWithFallback = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  return (
    <div
      className={
        nested
          ? 'flex flex-col gap-2 rounded-md border border-[var(--color-border-2)] p-2'
          : 'flex flex-col gap-2'
      }
    >
      <div className="grid grid-cols-[2rem_minmax(0,1fr)_2rem] items-center gap-2">
        <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-sm font-semibold text-[var(--color-primary)]">
          {row.ref}
        </span>
        <Select
          allowClear
          className="min-w-0"
          showSearch
          value={row.metricName}
          loading={metricsLoading}
          placeholder={t('monitor.metric')}
          options={metricOptions}
          filterOption={(input, option) =>
            (option?.label || '')
              .toString()
              .toLowerCase()
              .includes(input.toLowerCase())
          }
          onChange={(value) => onMetricChange(value)}
        />
        {canDelete ? (
          <Tooltip title={t('common.delete')}>
            <Button
              aria-label={t('common.delete')}
              className="h-8 w-8"
              icon={<CloseOutlined />}
              onClick={onRemove}
            />
          </Tooltip>
        ) : (
          <span className="h-8 w-8" />
        )}
      </div>
      <div
        className={
          showDimension
            ? 'ml-10 grid grid-cols-[132px_minmax(0,1fr)] items-center gap-2'
            : 'ml-10 grid grid-cols-[132px] items-center gap-2'
        }
      >
        <Select
          className="w-full"
          value={row.groupAlgorithm || 'avg'}
          placeholder={t('monitor.events.groupAggregationMethod')}
          options={groupMethodOptions}
          onChange={onGroupAlgorithmChange}
        />
        {showDimension ? (
          <Select
            allowClear
            className="min-w-0"
            mode="multiple"
            showSearch
            value={row.groupBy}
            placeholder={t('monitor.events.groupDimension')}
            options={dimensionOptions}
            onChange={(value) => onGroupByChange(sanitizeGroupBy(value))}
          />
        ) : null}
      </div>
      <div className="ml-10 flex flex-col gap-2">
        {row.filters.map((filter, filterIndex) => (
          <div className="flex flex-col gap-2" key={`${row.ref}-${filterIndex}`}>
            <div className="grid grid-cols-[82px_minmax(0,1fr)_2rem] items-center gap-2">
              {filterIndex > 0 ? (
                <Select
                  className="w-[82px] shrink-0"
                  value={filter.logic || 'and'}
                  options={[
                    { label: 'AND', value: 'and' },
                    { label: 'OR', value: 'or' }
                  ]}
                  onChange={(value) => onFilterChange(filterIndex, { logic: value })}
                />
              ) : (
                <span className="w-[82px] shrink-0 text-xs text-[var(--color-text-3)]">
                  {t('monitor.events.conditionDimension')}
                </span>
              )}
              <Select
                className="min-w-0"
                showSearch
                value={filter.name}
                placeholder={t('monitor.label')}
                options={labelOptions}
                onChange={(value) => onFilterChange(filterIndex, { name: value })}
              />
              <Tooltip title={t('common.delete')}>
                <Button
                  aria-label={t('common.delete')}
                  className="h-8 w-8"
                  icon={<CloseOutlined />}
                  onClick={() => onFilterRemove(filterIndex)}
                />
              </Tooltip>
            </div>
            <div className="ml-[90px] grid grid-cols-[104px_minmax(0,1fr)] items-center gap-2">
              <Select
                className="w-full"
                value={filter.method}
                placeholder={t('monitor.term')}
                options={conditionMethodOptions}
                onChange={(value) => onFilterChange(filterIndex, { method: value })}
              />
              <Input
                className="min-w-0"
                value={filter.value}
                placeholder={t('monitor.value')}
                onChange={(event) =>
                  onFilterChange(filterIndex, { value: event.target.value })
                }
              />
            </div>
          </div>
        ))}
        <Button className="w-fit" icon={<PlusOutlined />} onClick={onFilterAdd}>
          {translateWithFallback('monitor.events.multiAddFilter', '添加筛选')}
        </Button>
      </div>
    </div>
  );
};

export default MetricOperandRow;
