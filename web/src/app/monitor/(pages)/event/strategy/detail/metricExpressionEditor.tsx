'use client';

import React, { useMemo } from 'react';
import { Button, Input, Select, Tooltip } from 'antd';
import { CloseOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  FilterItem,
  IndexViewItem,
  ListItem,
  MetricItem
} from '@/app/monitor/types';
import {
  getMetricDimensionNames,
  sanitizeGroupBy
} from '@/app/monitor/utils/metricDimensions';
import { MetricExpressionRow } from './metricExpressionTypes';
import {
  createMetricRow,
  MetricExpressionMode,
  shouldShowFormulaEditor,
  VARIABLE_SEQUENCE
} from './formulaExpressionUtils';

interface MetricExpressionEditorProps {
  rows: MetricExpressionRow[];
  mode: MetricExpressionMode;
  resultName: string;
  expression: string;
  labelsByRef: Record<string, string[]>;
  originMetricData: IndexViewItem[];
  groupByOptions: string[];
  groupMethods: ListItem[];
  conditionMethods: ListItem[];
  metricsLoading: boolean;
  onRowsChange: (rows: MetricExpressionRow[]) => void;
  onResultNameChange: (value: string) => void;
  onExpressionChange: (value: string) => void;
}

const MetricExpressionEditor: React.FC<MetricExpressionEditorProps> = ({
  rows,
  mode,
  resultName,
  expression,
  labelsByRef,
  originMetricData,
  groupByOptions,
  groupMethods,
  conditionMethods,
  metricsLoading,
  onRowsChange,
  onResultNameChange,
  onExpressionChange
}) => {
  const { t } = useTranslation();
  const showFormula = shouldShowFormulaEditor(mode);

  const metricByName = useMemo(() => {
    const map = new Map<string, MetricItem>();
    originMetricData.forEach((group) => {
      (group.child || []).forEach((metric: MetricItem) => {
        map.set(metric.name, metric);
      });
    });
    return map;
  }, [originMetricData]);

  const metricOptions = useMemo(
    () =>
      originMetricData.map((group) => ({
        label: group.display_name,
        title: group.name,
        options: (group.child || []).map((metric: MetricItem) => ({
          label: metric.display_name,
          value: metric.name
        }))
      })),
    [originMetricData]
  );

  const updateRow = (rowIndex: number, patch: Partial<MetricExpressionRow>) => {
    onRowsChange(
      rows.map((row, index) =>
        index === rowIndex ? { ...row, ...patch } : row
      )
    );
  };

  const updateCondition = (
    rowIndex: number,
    conditionIndex: number,
    patch: Partial<FilterItem>
  ) => {
    const row = rows[rowIndex];
    const filters = row.filters.map((filter, index) =>
      index === conditionIndex ? { ...filter, ...patch } : filter
    );
    updateRow(rowIndex, { filters });
  };

  const normalizeFilters = (filters: FilterItem[]): FilterItem[] =>
    filters.map((filter, index) => ({
      ...filter,
      logic: index === 0 ? undefined : filter.logic || 'and'
    }));

  const addCondition = (rowIndex: number) => {
    const row = rows[rowIndex];
    updateRow(rowIndex, {
      filters: normalizeFilters([
        ...row.filters,
        {
          logic: row.filters.length ? 'and' : undefined,
          name: null,
          method: null,
          value: ''
        }
      ])
    });
  };

  const removeCondition = (rowIndex: number, conditionIndex: number) => {
    const row = rows[rowIndex];
    updateRow(rowIndex, {
      filters: normalizeFilters(
        row.filters.filter((_, index) => index !== conditionIndex)
      )
    });
  };

  const handleMetricChange = (rowIndex: number, metricName?: string) => {
    const target = metricName ? metricByName.get(metricName) : undefined;
    const labels = getMetricDimensionNames(target?.dimensions);
    const nextGroupBy = target
      ? sanitizeGroupBy([...groupByOptions, ...labels])
      : groupByOptions;
    updateRow(rowIndex, {
      metricName,
      metricId: target?.id || null,
      filters: [],
      groupBy: nextGroupBy
    });
  };

  const addMetricRow = () => {
    const usedRefs = new Set(rows.map((row) => row.ref));
    const nextRef =
      VARIABLE_SEQUENCE.find((ref) => !usedRefs.has(ref)) || `m${rows.length + 1}`;
    onRowsChange([
      ...rows,
      createMetricRow(0, {
        ref: nextRef,
        groupBy: groupByOptions.length ? groupByOptions : ['instance_id']
      })
    ]);
  };

  const removeMetricRow = (rowIndex: number) => {
    onRowsChange(rows.filter((_, index) => index !== rowIndex));
  };

  const getRowGroupByOptions = (row: MetricExpressionRow) =>
    sanitizeGroupBy([...groupByOptions, ...(labelsByRef[row.ref] || [])]).map(
      (item) => ({ label: item, value: item })
    );

  const translateWithFallback = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const groupMethodOptions = groupMethods.map((item) => ({
    label: `${item.label.toString().toLowerCase()} by`,
    value: item.value
  }));

  return (
    <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)]">
      <div className="flex min-h-11 items-center justify-between border-b border-[var(--color-border-2)] px-3">
        <span className="text-sm font-medium text-[var(--color-text-1)]">
          {translateWithFallback('monitor.events.metricEditor', '指标编辑器')}
        </span>
        {showFormula && (
          <span className="rounded border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-2 py-0.5 text-xs text-[var(--color-text-2)]">
            {translateWithFallback('monitor.events.expression', '表达式')}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-3">
        {rows.map((row, rowIndex) => (
          <div
            key={row.ref}
            className="mx-3 mt-3 rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-3"
          >
            <div className="flex flex-col gap-2">
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
                  onChange={(value) => handleMetricChange(rowIndex, value)}
                />
                {rows.length > 1 ? (
                  <Tooltip title={t('common.delete')}>
                    <Button
                      aria-label={t('common.delete')}
                      className="h-8 w-8"
                      icon={<CloseOutlined />}
                      onClick={() => removeMetricRow(rowIndex)}
                    />
                  </Tooltip>
                ) : (
                  <span className="h-8 w-8" />
                )}
              </div>
              <div className="ml-10 grid grid-cols-[132px_minmax(0,1fr)] items-center gap-2">
                <Select
                  className="w-full"
                  value={row.groupAlgorithm || 'avg'}
                  placeholder={t('monitor.events.groupAggregationMethod')}
                  options={groupMethodOptions}
                  onChange={(value) =>
                    updateRow(rowIndex, { groupAlgorithm: value })
                  }
                />
                <Select
                  allowClear
                  className="min-w-0"
                  maxTagCount="responsive"
                  mode="multiple"
                  showSearch
                  value={row.groupBy}
                  placeholder={t('monitor.events.groupDimension')}
                  options={getRowGroupByOptions(row)}
                  onChange={(value) =>
                    updateRow(rowIndex, { groupBy: sanitizeGroupBy(value) })
                  }
                />
              </div>
            </div>
            <div className="ml-10 mt-2 flex flex-col gap-2">
              {row.filters.map((filter, filterIndex) => (
                <div
                  className="flex flex-col gap-2"
                  key={`${row.ref}-${filterIndex}`}
                >
                  <div className="grid grid-cols-[82px_minmax(0,1fr)_2rem] items-center gap-2">
                    {filterIndex > 0 ? (
                      <Select
                        className="w-[82px] shrink-0"
                        value={filter.logic || 'and'}
                        options={[
                          { label: 'AND', value: 'and' },
                          { label: 'OR', value: 'or' }
                        ]}
                        onChange={(value) =>
                          updateCondition(rowIndex, filterIndex, {
                            logic: value
                          })
                        }
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
                      options={(labelsByRef[row.ref] || []).map((item) => ({
                        label: item,
                        value: item
                      }))}
                      onChange={(value) =>
                        updateCondition(rowIndex, filterIndex, { name: value })
                      }
                    />
                    <Tooltip title={t('common.delete')}>
                      <Button
                        aria-label={t('common.delete')}
                        className="h-8 w-8"
                        icon={<CloseOutlined />}
                        onClick={() => removeCondition(rowIndex, filterIndex)}
                      />
                    </Tooltip>
                  </div>
                  <div className="ml-[90px] grid grid-cols-[104px_minmax(0,1fr)] items-center gap-2">
                    <Select
                      className="w-full"
                      value={filter.method}
                      placeholder={t('monitor.term')}
                      options={conditionMethods.map((item) => ({
                        label: item.name,
                        value: item.id
                      }))}
                      onChange={(value) =>
                        updateCondition(rowIndex, filterIndex, {
                          method: value
                        })
                      }
                    />
                    <Input
                      className="min-w-0"
                      value={filter.value}
                      placeholder={t('monitor.value')}
                      onChange={(event) =>
                        updateCondition(rowIndex, filterIndex, {
                          value: event.target.value
                        })
                      }
                    />
                  </div>
                </div>
              ))}
              <Button
                className="w-fit"
                icon={<PlusOutlined />}
                onClick={() => addCondition(rowIndex)}
              >
                {t('monitor.addCondition')}
              </Button>
            </div>
          </div>
        ))}
        <Button
          className="mx-3 w-fit"
          icon={<PlusOutlined />}
          onClick={addMetricRow}
          type="dashed"
        >
          {translateWithFallback('monitor.events.addMetric', '添加指标')}
        </Button>
        {showFormula && (
          <div className="grid grid-cols-[2rem_minmax(0,220px)_16px_minmax(0,1fr)] items-center gap-2 border-t border-[var(--color-border-2)] px-3 py-3">
            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-xs font-semibold text-[var(--color-primary)]">
              fx
            </span>
            <Input
              className="min-w-0"
              value={resultName}
              placeholder={t('monitor.events.formulaResultNamePlaceholder')}
              onChange={(event) => onResultNameChange(event.target.value)}
            />
            <span className="text-center text-[var(--color-text-3)]">=</span>
            <Input
              className="min-w-0"
              value={expression}
              placeholder="a / b * 100"
              onChange={(event) => onExpressionChange(event.target.value)}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default MetricExpressionEditor;
