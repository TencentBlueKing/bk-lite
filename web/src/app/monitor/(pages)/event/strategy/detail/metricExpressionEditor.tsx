'use client';

import React, { useMemo } from 'react';
import { Button, Cascader, Input, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  FilterItem,
  IndexViewItem,
  ListItem,
  MetricItem,
  CascaderItem,
  UnitListItem
} from '@/app/monitor/types';
import { findCascaderPath } from '@/app/monitor/utils/common';
import {
  getMetricDimensionNames,
  sanitizeGroupBy
} from '@/app/monitor/utils/metricDimensions';
import { MetricExpressionRow } from './metricExpressionTypes';
import {
  alignFollowerGroupBy,
  groupByAfterSelectingMetric,
  ConditionSource,
  createMetricRow,
  DEFAULT_MULTI_LEVEL_THRESHOLD,
  MetricExpressionMode,
  shouldShowConditionSourceSwitch,
  shouldShowFormulaEditor,
  switchConditionSource,
  VARIABLE_SEQUENCE
} from './formulaExpressionUtils';
import MetricConditionCard from './metricConditionCard';
import MetricOperandRow from './metricOperandRow';
import {
  buildMetricSelectOption,
  PER_SERIES_ALGORITHMS,
  resolveEffectiveCalculationUnit
} from './strategyDetailUtils';

interface MetricExpressionEditorProps {
  id?: string;
  rows: MetricExpressionRow[];
  mode: MetricExpressionMode;
  resultName: string;
  expression: string;
  resultUnit: string | null;
  groupedUnitOptions: CascaderItem[];
  unitList: UnitListItem[];
  labelsByRef: Record<string, string[]>;
  originMetricData: IndexViewItem[];
  groupByOptions: string[];
  groupMethods: ListItem[];
  conditionMethods: ListItem[];
  algorithmOptions?: ListItem[];
  metricsLoading: boolean;
  onRowsChange: (rows: MetricExpressionRow[]) => void;
  onSourceChange?: (source: ConditionSource) => void;
  onResultNameChange: (value: string) => void;
  onExpressionChange: (value: string) => void;
  onResultUnitChange: (value: string) => void;
}

const MetricExpressionEditor: React.FC<MetricExpressionEditorProps> = ({
  id,
  rows,
  mode,
  resultName,
  expression,
  resultUnit,
  groupedUnitOptions,
  unitList,
  labelsByRef,
  originMetricData,
  groupByOptions,
  groupMethods,
  conditionMethods,
  algorithmOptions = [],
  metricsLoading,
  onRowsChange,
  onSourceChange,
  onResultNameChange,
  onExpressionChange,
  onResultUnitChange
}) => {
  const { t } = useTranslation();
  const showFormula = shouldShowFormulaEditor(mode);
  const showMulti = mode === 'multi';
  const showSourceSwitch = shouldShowConditionSourceSwitch(
    showMulti ? 'multi' : 'single'
  );
  const conditionSource: ConditionSource = showFormula ? 'formula' : 'metric';

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
        options: (group.child || []).map((metric: MetricItem) =>
          buildMetricSelectOption(metric, unitList)
        )
      })),
    [originMetricData, unitList]
  );

  const mergeRow = (
    row: MetricExpressionRow,
    patch: Partial<MetricExpressionRow>
  ): MetricExpressionRow => {
    const next = { ...row, ...patch };
    if (next.source === 'formula' && patch.groupBy && !patch.operands) {
      const allowed = patch.groupBy;
      next.operands = (next.operands || []).map((operand, index) => {
        if (index === 0) {
          return { ...operand, groupBy: allowed };
        }
        const kept = (operand.groupBy || []).filter((item) => allowed.includes(item));
        return { ...operand, groupBy: kept.length ? kept : allowed };
      });
    }
    return next;
  };

  const updateRow = (rowIndex: number, patch: Partial<MetricExpressionRow>) => {
    if ((showMulti || showFormula) && rowIndex === 0 && patch.groupBy) {
      const aligned = alignFollowerGroupBy(rows, patch.groupBy);
      onRowsChange(
        aligned.map((row, index) =>
          index === rowIndex ? mergeRow(row, patch) : row
        )
      );
      return;
    }
    onRowsChange(
      rows.map((row, index) =>
        index === rowIndex ? mergeRow(row, patch) : row
      )
    );
  };

  const replaceRow = (rowIndex: number, next: MetricExpressionRow) => {
    onRowsChange(rows.map((row, index) => (index === rowIndex ? next : row)));
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
    const availableGroupBy = target
      ? sanitizeGroupBy([...groupByOptions, ...labels])
      : groupByOptions;
    const anchorGroupBy = rows[0]?.groupBy || [];
    const nextGroupBy = groupByAfterSelectingMetric(
      availableGroupBy,
      anchorGroupBy,
      rowIndex > 0 && (showMulti || showFormula)
    );
    const metricUnit =
      resolveEffectiveCalculationUnit({
        isFormulaMode: false,
        unit: target?.unit,
        unitList
      }) || '';
    updateRow(rowIndex, {
      metricName,
      metricLabel: target?.display_name || target?.name || metricName,
      metricId: target?.id || null,
      filters: [],
      groupBy: nextGroupBy,
      ...(showMulti
        ? {
          metricUnit,
          calculationUnit: metricUnit,
          thresholdUnit: metricUnit
        }
        : {})
    });
  };

  const handleOperandMetricChange = (
    rowIndex: number,
    operandIndex: number,
    metricName?: string
  ) => {
    const target = metricName ? metricByName.get(metricName) : undefined;
    const row = rows[rowIndex];
    const operands = (row.operands || []).map((operand, index) =>
      index === operandIndex
        ? {
          ...operand,
          metricName,
          metricLabel: target?.display_name || target?.name || metricName,
          metricId: target?.id || null,
          filters: []
        }
        : operand
    );
    updateRow(rowIndex, { operands });
  };

  const updateOperand = (
    rowIndex: number,
    operandIndex: number,
    patch: Partial<MetricExpressionRow>
  ) => {
    const row = rows[rowIndex];
    updateRow(rowIndex, {
      operands: (row.operands || []).map((operand, index) =>
        index === operandIndex ? { ...operand, ...patch } : operand
      )
    });
  };

  const addOperand = (rowIndex: number) => {
    const row = rows[rowIndex];
    const operands = row.operands || [];
    updateRow(rowIndex, {
      operands: [
        ...operands,
        createMetricRow(operands.length, {
          ref: `${row.ref}${operands.length + 1}`,
          groupAlgorithm: 'sum',
          groupBy: operands[0]?.groupBy?.length ? operands[0].groupBy : row.groupBy
        })
      ]
    });
  };

  const removeOperand = (rowIndex: number, operandIndex: number) => {
    const row = rows[rowIndex];
    updateRow(rowIndex, {
      operands: (row.operands || []).filter((_, index) => index !== operandIndex)
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
        groupBy: rows[0]?.groupBy?.length
          ? rows[0].groupBy
          : groupByOptions.length
            ? groupByOptions
            : ['instance_id'],
        ...(showMulti
          ? {
            role: 'level' as const,
            algorithm: 'avg_over_time',
            threshold: DEFAULT_MULTI_LEVEL_THRESHOLD.map((item) => ({
              ...item
            }))
          }
          : {})
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
    label: `${String(item.label ?? '').toLowerCase()} by`,
    value: String(item.value ?? '')
  }));
  const conditionMethodOptions = conditionMethods.map((item) => ({
    label: String(item.name || ''),
    value: String(item.id ?? '')
  }));
  const labelOptionsFor = (row: MetricExpressionRow) =>
    (labelsByRef[row.ref] || []).map((item) => ({ label: item, value: item }));
  const dimensionOptionsFor = (row: MetricExpressionRow, rowIndex: number) => {
    if (rowIndex > 0 && (showMulti || showFormula)) {
      return (rows[0]?.groupBy || []).map((item) => ({
        label: item,
        value: item
      }));
    }
    return getRowGroupByOptions(row);
  };

  const operandDimensionOptions = (
    row: MetricExpressionRow,
    rowIndex: number,
    operand: MetricExpressionRow,
    operandIndex: number
  ) => {
    if (operandIndex > 0) {
      return (row.operands?.[0]?.groupBy || row.groupBy || []).map((item) => ({
        label: item,
        value: item
      }));
    }
    return dimensionOptionsFor(operand, rowIndex);
  };

  const updateOperandGroupBy = (
    rowIndex: number,
    operandIndex: number,
    groupBy: string[]
  ) => {
    const row = rows[rowIndex];
    const operands = row.operands || [];
    const nextGroupBy = sanitizeGroupBy(groupBy);
    if (operandIndex === 0) {
      const nextOperands = operands.map((operand, index) => {
        if (index === 0) {
          return { ...operand, groupBy: nextGroupBy };
        }
        const kept = (operand.groupBy || []).filter((item) => nextGroupBy.includes(item));
        return { ...operand, groupBy: kept.length ? kept : nextGroupBy };
      });
      updateRow(rowIndex, { groupBy: nextGroupBy, operands: nextOperands });
      return;
    }
    const allowed = operands[0]?.groupBy || row.groupBy;
    const kept = nextGroupBy.filter((item) => allowed.includes(item));
    updateRow(rowIndex, {
      operands: operands.map((operand, index) =>
        index === operandIndex ? { ...operand, groupBy: kept } : operand
      )
    });
  };

  const renderOperand = (
    row: MetricExpressionRow,
    rowIndex: number,
    options: { showDimension: boolean; nested?: boolean; canDelete: boolean }
  ) => (
    <MetricOperandRow
      row={row}
      metricOptions={metricOptions}
      metricsLoading={metricsLoading}
      groupMethodOptions={groupMethodOptions}
      conditionMethodOptions={conditionMethodOptions}
      labelOptions={labelOptionsFor(row)}
      showDimension={options.showDimension}
      dimensionOptions={dimensionOptionsFor(row, rowIndex)}
      canDelete={options.canDelete}
      nested={options.nested}
      onMetricChange={(value) => handleMetricChange(rowIndex, value)}
      onGroupAlgorithmChange={(value) =>
        updateRow(rowIndex, { groupAlgorithm: value })
      }
      onGroupByChange={(value) => updateRow(rowIndex, { groupBy: value })}
      onFilterChange={(filterIndex, patch) =>
        updateCondition(rowIndex, filterIndex, patch)
      }
      onFilterRemove={(filterIndex) => removeCondition(rowIndex, filterIndex)}
      onFilterAdd={() => addCondition(rowIndex)}
      onRemove={() => removeMetricRow(rowIndex)}
    />
  );

  const renderMultiFields = (row: MetricExpressionRow, rowIndex: number) => (
    <div
      className={
        row.source === 'formula'
          ? 'ml-12 grid grid-cols-[132px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2'
          : 'ml-10 grid grid-cols-[132px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2'
      }
    >
      <Select
        className="w-full"
        value={row.role || 'level'}
        options={[
          {
            label: translateWithFallback('monitor.events.multiRoleLevel', '常规'),
            value: 'level'
          },
          {
            label: translateWithFallback('monitor.events.multiRoleGate', '前置条件'),
            value: 'gate'
          }
        ]}
        onChange={(value) =>
          updateRow(rowIndex, {
            role: value,
            threshold:
              value === 'gate'
                ? [{ method: '>', value: null }]
                : row.threshold?.some((item) => item.level)
                  ? row.threshold
                  : DEFAULT_MULTI_LEVEL_THRESHOLD.map((item) => ({ ...item }))
          })
        }
      />
      <Select
        className="w-full"
        value={row.algorithm || 'avg_over_time'}
        options={(row.source === 'formula'
          ? algorithmOptions.filter(
            (item) => !PER_SERIES_ALGORITHMS.includes(String(item.value ?? ''))
          )
          : algorithmOptions
        ).map((item) => ({
          label: String(item.label ?? ''),
          value: String(item.value ?? '')
        }))}
        onChange={(value) => updateRow(rowIndex, { algorithm: String(value) })}
      />
      <Cascader
        className="w-full"
        showSearch
        allowClear={false}
        value={
          row.thresholdUnit
            ? findCascaderPath(groupedUnitOptions, row.thresholdUnit)
            : []
        }
        options={groupedUnitOptions}
        placeholder={translateWithFallback('monitor.events.formulaResultUnit', '单位')}
        onChange={(path) => {
          const unit = String(path[path.length - 1] || '');
          updateRow(rowIndex, {
            calculationUnit: unit,
            thresholdUnit: unit
          });
        }}
      />
    </div>
  );

  const formulaResultRow = (
    <div className="grid grid-cols-[2rem_minmax(0,220px)_16px_minmax(0,1fr)_96px] items-center gap-2">
      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-xs font-semibold text-[var(--color-primary)]">
        fx
      </span>
      <Input
        className="min-w-0"
        value={resultName}
        placeholder={t('monitor.integrations.formulaResultNamePlaceholder')}
        onChange={(event) => onResultNameChange(event.target.value)}
      />
      <span className="text-center text-[var(--color-text-3)]">=</span>
      <Input
        className="min-w-0"
        value={expression}
        placeholder="a / b * 100"
        onChange={(event) => onExpressionChange(event.target.value)}
      />
      <Cascader
        className="w-full"
        showSearch
        allowClear={false}
        value={resultUnit ? findCascaderPath(groupedUnitOptions, resultUnit) : []}
        aria-label={translateWithFallback(
          'monitor.events.formulaResultUnit',
          '结果单位'
        )}
        placeholder={translateWithFallback(
          'monitor.events.formulaResultUnit',
          '结果单位'
        )}
        options={groupedUnitOptions}
        onChange={(path) => {
          const next = (path as (string | number)[]).at(-1);
          if (typeof next === 'string') {
            onResultUnitChange(next);
          }
        }}
      />
    </div>
  );

  const primaryRow = rows[0];

  return (
    <div
      id={id}
      className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] shadow-sm"
    >
      <div className="flex min-h-11 items-center justify-between border-b border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-3">
        <span className="text-sm font-medium text-[var(--color-text-1)]">
          {translateWithFallback('monitor.events.metricEditor', '指标编辑器')}
        </span>
        {showFormula && (
          <span className="rounded border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-2 py-0.5 text-xs text-[var(--color-text-2)]">
            {translateWithFallback('monitor.events.expression', '表达式')}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-3 pb-3">
        {showFormula && primaryRow ? (
          <MetricConditionCard
            showSourceSwitch={showSourceSwitch}
            source={conditionSource}
            onSourceChange={onSourceChange}
          >
            {rows.map((row, rowIndex) => (
              <div key={row.ref}>
                {renderOperand(row, rowIndex, {
                  showDimension: true,
                  nested: true,
                  canDelete: rows.length > 1
                })}
              </div>
            ))}
            <Button
              className="w-fit"
              icon={<PlusOutlined />}
              onClick={addMetricRow}
              type="dashed"
            >
              {translateWithFallback('monitor.events.addMetric', '添加指标')}
            </Button>
            {formulaResultRow}
          </MetricConditionCard>
        ) : null}
        {showMulti
          ? rows.map((row, rowIndex) => (
              <MetricConditionCard
                key={row.ref}
                showSourceSwitch={showSourceSwitch}
                source={row.source === 'formula' ? 'formula' : 'metric'}
                onSourceChange={(source) =>
                  replaceRow(rowIndex, switchConditionSource(row, source))
                }
                note={
                  rowIndex === 0
                    ? translateWithFallback(
                      'monitor.events.multiAlignHint',
                      '其余条件按第一条的实例对齐'
                    )
                    : undefined
                }
              >
                {row.source === 'formula' ? (
                  <>
                    {(row.operands || []).map((operand, operandIndex) => (
                      <MetricOperandRow
                        key={operand.ref}
                        row={operand}
                        metricOptions={metricOptions}
                        metricsLoading={metricsLoading}
                        groupMethodOptions={groupMethodOptions}
                        conditionMethodOptions={conditionMethodOptions}
                        labelOptions={(labelsByRef[operand.ref] || []).map((item) => ({
                          label: item,
                          value: item
                        }))}
                        showDimension
                        dimensionOptions={operandDimensionOptions(
                          row,
                          rowIndex,
                          operand,
                          operandIndex
                        )}
                        canDelete={(row.operands || []).length > 2}
                        nested
                        onMetricChange={(value) =>
                          handleOperandMetricChange(rowIndex, operandIndex, value)
                        }
                        onGroupAlgorithmChange={(value) =>
                          updateOperand(rowIndex, operandIndex, { groupAlgorithm: value })
                        }
                        onGroupByChange={(value) =>
                          updateOperandGroupBy(rowIndex, operandIndex, value)
                        }
                        onFilterChange={(filterIndex, patch) => {
                          const filters = operand.filters.map((filter, index) =>
                            index === filterIndex ? { ...filter, ...patch } : filter
                          );
                          updateOperand(rowIndex, operandIndex, { filters });
                        }}
                        onFilterRemove={(filterIndex) =>
                          updateOperand(rowIndex, operandIndex, {
                            filters: operand.filters.filter((_, index) => index !== filterIndex)
                          })
                        }
                        onFilterAdd={() =>
                          updateOperand(rowIndex, operandIndex, {
                            filters: [
                              ...operand.filters,
                              {
                                logic: operand.filters.length ? 'and' : undefined,
                                name: null,
                                method: null,
                                value: ''
                              }
                            ]
                          })
                        }
                        onRemove={() => removeOperand(rowIndex, operandIndex)}
                      />
                    ))}
                    <Button
                      className="w-fit"
                      icon={<PlusOutlined />}
                      onClick={() => addOperand(rowIndex)}
                      type="dashed"
                    >
                      {translateWithFallback('monitor.events.addMetric', '添加指标')}
                    </Button>
                    <div className="grid grid-cols-[2rem_minmax(0,220px)_16px_minmax(0,1fr)] items-center gap-2">
                      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-xs font-semibold text-[var(--color-primary)]">
                        fx
                      </span>
                      <Input
                        className="min-w-0"
                        value={row.resultName || ''}
                        placeholder={t('monitor.integrations.formulaResultNamePlaceholder')}
                        onChange={(event) =>
                          updateRow(rowIndex, { resultName: event.target.value })
                        }
                      />
                      <span className="text-center text-[var(--color-text-3)]">=</span>
                      <Input
                        className="min-w-0"
                        value={row.expression || ''}
                        placeholder="a1 / a2 * 100"
                        onChange={(event) =>
                          updateRow(rowIndex, { expression: event.target.value })
                        }
                      />
                    </div>
                  </>
                ) : (
                  renderOperand(row, rowIndex, {
                    showDimension: true,
                    canDelete: rows.length > 2
                  })
                )}
                {renderMultiFields(row, rowIndex)}
              </MetricConditionCard>
          ))
          : null}
        {!showFormula && !showMulti && primaryRow ? (
          <MetricConditionCard
            showSourceSwitch={showSourceSwitch}
            source={conditionSource}
            onSourceChange={onSourceChange}
          >
            {renderOperand(primaryRow, 0, {
              showDimension: true,
              canDelete: false
            })}
          </MetricConditionCard>
        ) : null}
        {showMulti ? (
          <Button
            className="mx-3 w-fit"
            disabled={rows.length >= 5}
            icon={<PlusOutlined />}
            onClick={addMetricRow}
            type="dashed"
          >
            {translateWithFallback('monitor.events.multiAddCondition', '添加条件')}
          </Button>
        ) : null}
        {showMulti ? (
          <div className="mx-3 flex items-center gap-2">
            <span className="shrink-0 text-[var(--color-text-2)]">
              {t('monitor.events.multiDisplayMetricName')}
            </span>
            <Input
              value={resultName}
              placeholder={t('monitor.events.multiDisplayMetricNamePlaceholder')}
              onChange={(event) => onResultNameChange(event.target.value)}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default MetricExpressionEditor;
