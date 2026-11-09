'use client';

import React from 'react';
import { Button, Input, InputNumber, Radio, Select } from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { ConditionFilterProps } from '@/app/log/types/event';
import { FilterItem } from '@/app/log/types/integration';
import { ListItem } from '@/app/log/types';
import { useTranslation } from '@/utils/i18n';
import { cloneDeep } from 'lodash';
import {
  AggregateFunctionOption,
  COMPARE_KIND_LIST,
  COMPARE_OFFSET_METHOD_LIST,
  FUNCTION_LIST,
  LEVEL_MAP,
  QUANTILE_LIST,
} from '@/app/log/constants';
import { useAggregateOperatorList, useConditionList } from '@/app/log/hooks/event';
import { compareOffsetLimit, presentCompare } from '@/app/log/utils/compareTarget';
import {
  conditionWithLadderSlots,
  displayedThresholdSlots,
  DISPLAY_LEVELS,
  isNumericCompare,
  LADDER_OPS,
  thresholdsForOperator,
} from './policyFormUtils';

const { Option } = Select;

const MEMBERSHIP_OPS = new Set(['in', 'nin']);

const conditionLetter = (index: number) =>
  index < 26 ? String.fromCharCode(97 + index) : `a${index + 1}`;

const ConditionFieldRow = ({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) => (
  <div className={`grid min-w-0 grid-cols-[3rem_minmax(0,1fr)] items-start gap-2 ${className || ''}`}>
    <span className="flex min-h-8 items-center text-xs text-[var(--color-text-3)]">{label}</span>
    <div className="flex min-w-0 flex-col justify-center gap-1">{children}</div>
  </div>
);

const ConditionSelector: React.FC<ConditionFilterProps> = ({
  data = [],
  fields = [],
  term,
  onTermChange,
  onChange,
  section,
}) => {
  const { t } = useTranslation();
  const conditionList = useConditionList();
  const aggregateOperators = useAggregateOperatorList();

  const functionName = (item: AggregateFunctionOption) => t(item.labelKey);

  const functionMethod = (item: AggregateFunctionOption) => item.value.toUpperCase();

  const showFunctionMethod = (item: AggregateFunctionOption) =>
    functionName(item).trim().toUpperCase() !== functionMethod(item);

  const functionLabel = (item: AggregateFunctionOption) =>
    showFunctionMethod(item)
      ? `${functionName(item)}（${functionMethod(item)}）`
      : functionName(item);

  const levelLabel = (level: string) => t(`log.event.${level}`);

  const handleConditionChange = (extra: {
    val: string;
    index: number;
    field: 'op' | 'field' | 'func';
  }) => {
    const previous = data[extra.index];
    const newData = cloneDeep(data);
    if (extra.field === 'op') {
      newData[extra.index] = thresholdsForOperator(previous, extra.val);
    } else {
      newData[extra.index][extra.field] = extra.val;
    }
    if (extra.field === 'func') {
      const option = FUNCTION_LIST.find((item) => item.value === extra.val);
      if (option && !option.needsField) {
        newData[extra.index].field = '_msg';
      }
      if (option && option.comparable === false) {
        newData[extra.index].compare = { kind: 'absolute' };
      }
      const params = { ...(newData[extra.index].params || {}) };
      if (!option?.needsQuantile && params.quantile != null) {
        delete params.quantile;
      }
      if (!option?.needsFilter && params.filter != null) {
        delete params.filter;
      }
      newData[extra.index].params = params;
      const nextKind = presentCompare(newData[extra.index].compare).kind || 'absolute';
      if (isNumericCompare(extra.val, nextKind) && MEMBERSHIP_OPS.has(String(newData[extra.index].op))) {
        newData[extra.index].op = null;
        delete newData[extra.index].thresholds;
      }
    }
    onChange?.(newData);
  };

  const handleCompareKind = (kind: string, index: number) => {
    const newData = cloneDeep(data);
    const current = presentCompare(newData[index].compare);
    if (kind === 'absolute') {
      newData[index].compare = { kind: 'absolute' };
    } else {
      const to = current.to || 'previous_window';
      newData[index].compare = to === 'offset_hours' || to === 'offset_days'
        ? { kind, to, offset: current.offset || 1 }
        : { kind, to };
    }
    if (isNumericCompare(newData[index].func, kind) && MEMBERSHIP_OPS.has(String(newData[index].op))) {
      newData[index].op = null;
      delete newData[index].thresholds;
    }
    onChange?.(newData);
  };

  const handleCompareTarget = (target: string, index: number) => {
    const newData = cloneDeep(data);
    const current = presentCompare(newData[index].compare);
    const kind = current.kind || 'delta';
    if (target === 'offset_hours' || target === 'offset_days') {
      newData[index].compare = {
        kind,
        to: target,
        offset: current.to === target && current.offset ? current.offset : 1,
      };
    } else {
      newData[index].compare = { kind, to: target };
    }
    onChange?.(newData);
  };

  const handleOffset = (value: number | null, index: number) => {
    const newData = cloneDeep(data);
    const current = presentCompare(newData[index].compare);
    newData[index].compare = {
      kind: current.kind,
      to: current.to,
      offset: value == null ? undefined : Math.trunc(value),
    };
    onChange?.(newData);
  };

  const handleQuantile = (quantile: number, index: number) => {
    const newData = cloneDeep(data);
    newData[index].params = { ...(newData[index].params || {}), quantile };
    onChange?.(newData);
  };

  const handleRatioFilter = (
    event: React.ChangeEvent<HTMLInputElement>,
    index: number
  ) => {
    const newData = cloneDeep(data);
    newData[index].field = '_msg';
    newData[index].params = {
      ...(newData[index].params || {}),
      filter: event.target.value,
    };
    onChange?.(newData);
  };

  const handleValueChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    index: number
  ) => {
    const newData = [...data];
    newData[index] = { ...newData[index], value: e.target.value };
    onChange?.(newData);
  };

  const handleNumericValueChange = (val: number | string | null, index: number) => {
    const newData = [...data];
    newData[index] = { ...newData[index], value: String(val ?? '') };
    onChange?.(newData);
  };

  const handleLadderValueChange = (level: string, val: number | string | null, index: number) => {
    const slots = displayedThresholdSlots(data[index]);
    slots[level] = val == null || val === '' ? '' : String(val);
    const newData = [...data];
    newData[index] = conditionWithLadderSlots(data[index], slots);
    onChange?.(newData);
  };

  // 等于、不等于没有单调阶梯，级别由填进哪一档决定，不能再给整条条件另选一个级别。
  const handleExclusiveSlotChange = (level: string, val: number | string | null, index: number) => {
    const slots: Record<string, string> = { warning: '', error: '', critical: '' };
    if (val != null && val !== '') {
      slots[level] = String(val);
    }
    const newData = [...data];
    newData[index] = conditionWithLadderSlots(data[index], slots);
    onChange?.(newData);
  };

  const handleRoleChange = (role: string, index: number) => {
    const previous = data[index];
    const newData = cloneDeep(data);
    if (role === 'guard') {
      const slots = displayedThresholdSlots(previous);
      const filled = ['warning', 'error', 'critical']
        .map((level) => slots[level])
        .find((value) => value !== '') || previous.value || '';
      const next: FilterItem = {
        ...previous,
        role: 'guard',
        value: filled,
        compare: { kind: 'absolute' },
      };
      delete next.thresholds;
      newData[index] = next;
    } else {
      newData[index] = conditionWithLadderSlots(
        { ...previous, role: 'regular' },
        { warning: previous.value || '', error: '', critical: '' }
      );
    }
    onChange?.(newData);
  };

  const operatorChoices = (conditionItem: FilterItem) => {
    const compareKind = presentCompare(conditionItem.compare).kind || 'absolute';
    const numericCompare = isNumericCompare(conditionItem.func, compareKind);
    const operatorOptions = [...aggregateOperators];
    if (MEMBERSHIP_OPS.has(String(conditionItem.op)) && !numericCompare) {
      const currentOp = conditionList.find(
        (item) => String(item.id) === String(conditionItem.op)
      );
      if (currentOp) {
        operatorOptions.push(currentOp);
      }
    }
    return { numericCompare, operatorOptions };
  };

  const columnUnit = (conditionItem: FilterItem) => {
    const option = FUNCTION_LIST.find((item) => item.value === conditionItem.func);
    const kind = presentCompare(conditionItem.compare).kind || 'absolute';
    if (option?.unitKey) {
      return t(option.unitKey);
    }
    if (kind === 'percent' || conditionItem.func === 'ratio') {
      return '%';
    }
    return '';
  };

  const writeLevelSlot = (
    conditionItem: FilterItem,
    level: string,
    val: number | string | null,
    index: number
  ) => {
    const ladder = conditionItem.op == null || LADDER_OPS.has(String(conditionItem.op));
    if (ladder) {
      handleLadderValueChange(level, val, index);
      return;
    }
    handleExclusiveSlotChange(level, val, index);
  };

  const regularColumns = data
    .map((conditionItem, index) => ({ conditionItem, index }))
    .filter(({ conditionItem }) => conditionItem.role !== 'guard');

  const handleAddCondition = () => {
    const newData = [...data, { field: null, op: null, value: '' }];
    onChange?.(newData);
  };

  const handleDeleteCondition = (index: number) => {
    const newData = data.filter((_, i) => i !== index);
    onChange?.(newData);
  };

  const showDefinition = section !== 'levels';
  const showLevels = section !== 'definition';
  const levelColumnCount = Math.max(regularColumns.length, 1);
  const levelColumns = `64px repeat(${levelColumnCount}, minmax(180px, 1fr))`;
  const levelTrackMin = 64 + levelColumnCount * (180 + 12);

  return (
    <div className={showDefinition && showLevels ? 'flex flex-col gap-4' : undefined}>
      {showDefinition ? (
      <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] shadow-sm">
      <div className="flex min-h-11 flex-wrap items-center gap-2 border-b border-[var(--color-border-2)] px-3">
        <span>{t('log.event.matchPrefix')}</span>
        <Radio.Group
          name="log-policy-condition-term"
          aria-label={t('log.integration.rule')}
          optionType="button"
          size="small"
          value={term}
          onChange={(event) => onTermChange(event.target.value)}
          options={[
            { value: 'or', label: t('log.event.termAny') },
            { value: 'and', label: t('log.event.termAll') },
          ]}
        />
        <span>{t('log.event.matchSuffix')}</span>
      </div>
      <div className="flex flex-col gap-3 p-3">
        {data.map((conditionItem, index) => {
          const functionOption = FUNCTION_LIST.find(
            (item) => item.value === conditionItem.func
          );
          const legacyDelta = conditionItem.func === 'count_delta';
          const showField = !legacyDelta && (!functionOption || functionOption.needsField);
          const presentedCompare = presentCompare(conditionItem.compare);
          const compareKind = presentedCompare.kind || 'absolute';
          const comparable = functionOption ? functionOption.comparable !== false : !legacyDelta;
          const customOffset = presentedCompare.to === 'offset_hours' || presentedCompare.to === 'offset_days';
          const showPercent = compareKind === 'percent';
          const showRatio = functionOption?.needsFilter === true;
          const guard = conditionItem.role === 'guard';
          const { numericCompare, operatorOptions } = operatorChoices(conditionItem);
          const showTarget = comparable && !guard && compareKind !== 'absolute';
          return (
            <div
              className="grid grid-cols-[2rem_minmax(0,1fr)_2rem] items-center gap-2 rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg)] p-2"
              key={index}
            >
              <span
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-sm font-semibold text-[var(--color-primary)]"
                aria-label={t('log.event.conditionIndex', '条件 {index}', { index: index + 1 })}
              >
                {conditionLetter(index)}
              </span>
              <div className="grid min-w-0 grid-cols-2 gap-x-3">
              <ConditionFieldRow label={t('log.event.conditionRole')}>
                <Select
                  className="w-full"
                  aria-label={t('log.event.conditionRole')}
                  value={guard ? 'guard' : 'regular'}
                  options={[
                    { value: 'regular', label: t('log.event.roleRegular') },
                    { value: 'guard', label: t('log.event.roleGuard'), disabled: term === 'or' },
                  ]}
                  onChange={(val) => handleRoleChange(val, index)}
                />
              </ConditionFieldRow>
              <ConditionFieldRow label={t('log.event.statRow')}>
                <div className="flex min-w-0 items-center gap-2">
                  <Select
                    className="min-w-0 flex-1"
                    popupMatchSelectWidth={false}
                    placeholder={t('log.event.selectFunction')}
                    showSearch
                    optionLabelProp="label"
                    optionFilterProp="title"
                    value={conditionItem.func}
                    onChange={(val) =>
                      handleConditionChange({
                        val,
                        index,
                        field: 'func'
                      })
                    }
                  >
                    {FUNCTION_LIST.map((item) => (
                      <Option
                        value={item.value}
                        key={item.value}
                        label={functionName(item)}
                        title={functionLabel(item)}
                      >
                        <span className="text-[var(--color-text-1)]">{functionName(item)}</span>
                        {showFunctionMethod(item) ? (
                          <span className="text-[var(--color-text-3)]">
                            （{functionMethod(item)}）
                          </span>
                        ) : null}
                      </Option>
                    ))}
                  </Select>
                  {functionOption?.needsQuantile ? (
                    <Select
                      className="w-[5.5rem] shrink-0"
                      placeholder={t('log.event.quantileLabel')}
                      value={conditionItem.params?.quantile}
                      onChange={(val) => handleQuantile(val, index)}
                    >
                      {QUANTILE_LIST.map((item) => (
                        <Option value={item} key={item}>
                          {`P${Math.round(item * 100)}`}
                        </Option>
                      ))}
                    </Select>
                  ) : null}
                </div>
                {legacyDelta ? (
                  <span className="text-xs leading-5 text-[var(--color-text-3)]">
                    {t('log.event.countDeltaTip')}
                  </span>
                ) : null}
              </ConditionFieldRow>
              </div>
              {data.length > 1 ? (
                <Button
                  type="text"
                  className="h-8 w-8 min-w-0 shrink-0 px-0"
                  icon={<CloseOutlined />}
                  aria-label={t('log.event.deleteCondition')}
                  onClick={() => handleDeleteCondition(index)}
                />
              ) : (
                <span className="h-8 w-8" />
              )}
              <div className="col-start-2 grid min-w-0 grid-cols-2 gap-x-3 gap-y-2">
                {showField ? (
                  <ConditionFieldRow label={t('log.event.fieldRow')}>
                    <Select
                      className="w-full"
                      placeholder={t('log.event.selectField')}
                      showSearch
                      value={conditionItem.field}
                      onChange={(val) =>
                        handleConditionChange({
                          val,
                          index,
                          field: 'field'
                        })
                      }
                    >
                      {fields.map((item: string) => (
                        <Option value={item} key={item}>
                          {item}
                        </Option>
                      ))}
                    </Select>
                  </ConditionFieldRow>
                ) : null}
                {showRatio ? (
                  <ConditionFieldRow className="col-span-2" label={t('log.event.ratioNumerator')}>
                    <Input
                      placeholder={t('log.event.ratioFilter')}
                      value={conditionItem.params?.filter}
                      onChange={(event) => handleRatioFilter(event, index)}
                    />
                    <span className="text-xs leading-5 text-[var(--color-text-3)]">
                      {t('log.event.ratioFilterTip')}
                    </span>
                  </ConditionFieldRow>
                ) : null}
                {comparable ? (
                  <ConditionFieldRow label={t('log.event.compareRow')}>
                    <Select
                      className="w-full"
                      aria-label={t('log.event.compareKind')}
                      value={compareKind}
                      options={COMPARE_KIND_LIST.map((item) => ({
                        value: item.value,
                        label: t(item.labelKey),
                        disabled: guard && item.value !== 'absolute',
                      }))}
                      onChange={(val) => handleCompareKind(val, index)}
                    />
                    {showPercent ? (
                      <span className="text-xs leading-5 text-[var(--color-text-3)]">
                        {t('log.event.percentTip')}
                      </span>
                    ) : null}
                  </ConditionFieldRow>
                ) : null}
                {showTarget ? (
                  <ConditionFieldRow className="col-span-2" label={t('log.event.compareTo')}>
                    <div className="flex min-w-0 items-center gap-2">
                      <Select
                        className="min-w-0 flex-1"
                        aria-label={t('log.event.compareTo')}
                        value={presentedCompare.to}
                        onChange={(val) => handleCompareTarget(val, index)}
                      >
                        {COMPARE_OFFSET_METHOD_LIST.map((item) => (
                          <Option value={item.value} key={item.value}>
                            {t(item.labelKey)}
                          </Option>
                        ))}
                      </Select>
                      {customOffset ? (
                        <InputNumber
                          className="w-[9rem] shrink-0"
                          min={1}
                          max={compareOffsetLimit(presentedCompare.to)}
                          precision={0}
                          value={presentedCompare.offset}
                          aria-label={t(
                            presentedCompare.to === 'offset_days'
                              ? 'log.event.compareOffsetCountDay'
                              : 'log.event.compareOffsetCountHour'
                          )}
                          addonAfter={t(
                            presentedCompare.to === 'offset_days'
                              ? 'log.event.compareOffsetUnitDay'
                              : 'log.event.compareOffsetUnitHour'
                          )}
                          onChange={(value) => handleOffset(typeof value === 'number' ? value : null, index)}
                        />
                      ) : null}
                    </div>
                  </ConditionFieldRow>
                ) : null}
                {guard ? (
                  <ConditionFieldRow className="col-span-2" label={t('log.event.guardThreshold')}>
                    <div className="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-2">
                      <Select
                        className="w-full"
                        placeholder={t('log.event.selectCriteria')}
                        value={
                          MEMBERSHIP_OPS.has(String(conditionItem.op)) && numericCompare
                            ? undefined
                            : conditionItem.op
                        }
                        options={operatorOptions.map((item: ListItem) => ({
                          value: item.id,
                          label: item.name,
                        }))}
                        onChange={(val) =>
                          handleConditionChange({
                            val,
                            index,
                            field: 'op'
                          })
                        }
                      />
                      {numericCompare ? (
                        <InputNumber
                          className="w-full"
                          placeholder={t('log.event.enterThreshold')}
                          value={
                            Number.isFinite(Number(conditionItem.value)) && conditionItem.value !== ''
                              ? Number(conditionItem.value)
                              : null
                          }
                          onChange={(val) => handleNumericValueChange(val, index)}
                        />
                      ) : (
                        <Input
                          placeholder={t('log.event.enterThreshold')}
                          value={conditionItem.value}
                          onChange={(e) => handleValueChange(e, index)}
                        />
                      )}
                    </div>
                    <span className="text-xs leading-5 text-[var(--color-text-3)]">
                      {t('log.event.guardHint')}
                    </span>
                  </ConditionFieldRow>
                ) : null}
              </div>
            </div>
          );
        })}
        <Button
          type="dashed"
          icon={<PlusOutlined aria-hidden />}
          className="w-fit"
          onClick={handleAddCondition}
        >
          {t('log.event.addCondition')}
        </Button>
      </div>
      </div>
      ) : null}
      {showLevels ? (
      <div className="flex flex-col gap-2">
        <div
          className="w-full max-w-[560px] overflow-x-auto rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4 shadow-md"
          aria-label={t('log.event.levelSection')}
        >
          <div style={{ minWidth: `max(100%, ${levelTrackMin}px)` }}>
          <div className="grid items-center gap-x-3 pb-2" style={{ gridTemplateColumns: levelColumns }}>
            <span />
            {regularColumns.length ? regularColumns.map(({ conditionItem, index }) => {
              const option = FUNCTION_LIST.find((item) => item.value === conditionItem.func);
              const unit = columnUnit(conditionItem);
              return (
                <div key={`head-${index}`} className="flex min-w-0 items-center gap-1.5">
                  <span className="inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] px-1 font-mono text-xs font-semibold text-[var(--color-primary)]">
                    {conditionLetter(index)}
                  </span>
                  <span className="truncate text-xs text-[var(--color-text-2)]">{option ? functionName(option) : ''}</span>
                  {unit ? <span className="shrink-0 text-xs text-[var(--color-text-3)]">{unit}</span> : null}
                </div>
              );
            }) : <span />}
          </div>
          {DISPLAY_LEVELS.map((level) => (
            <div
              key={level}
              className="grid items-center gap-x-3 border-t border-[var(--color-border-1)] py-2"
              style={{ gridTemplateColumns: levelColumns }}
            >
              <span className="inline-flex items-center gap-2 text-sm text-[var(--color-text-1)]">
                <span
                  className="inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: LEVEL_MAP[level] }}
                />
                {levelLabel(level)}
              </span>
              {regularColumns.length ? regularColumns.map(({ conditionItem, index }) => {
                const { numericCompare, operatorOptions } = operatorChoices(conditionItem);
                const slots = displayedThresholdSlots(conditionItem);
                const useNumber = numericCompare || (conditionItem.op != null && LADDER_OPS.has(String(conditionItem.op)));
                return (
                  <div key={`${level}-${index}`} className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-center gap-1.5">
                    <Select
                      className="w-full"
                      popupMatchSelectWidth={false}
                      placeholder={t('log.event.selectCriteria')}
                      aria-label={`${conditionLetter(index)} ${levelLabel(level)} ${t('log.event.selectCriteria')}`}
                      value={
                        MEMBERSHIP_OPS.has(String(conditionItem.op)) && numericCompare
                          ? undefined
                          : conditionItem.op
                      }
                      options={operatorOptions.map((item: ListItem) => ({
                        value: item.id,
                        label: item.name,
                      }))}
                      onChange={(val) =>
                        handleConditionChange({
                          val,
                          index,
                          field: 'op'
                        })
                      }
                    />
                    {useNumber ? (
                      <InputNumber
                        className="w-full"
                        controls={false}
                        placeholder={t('log.event.enterThreshold')}
                        aria-label={levelLabel(level)}
                        value={
                          slots[level] !== '' && Number.isFinite(Number(slots[level]))
                            ? Number(slots[level])
                            : null
                        }
                        onChange={(val) => writeLevelSlot(conditionItem, level, val, index)}
                      />
                    ) : (
                      <Input
                        className="w-full"
                        placeholder={t('log.event.enterThreshold')}
                        aria-label={levelLabel(level)}
                        value={slots[level]}
                        onChange={(event) => writeLevelSlot(conditionItem, level, event.target.value, index)}
                      />
                    )}
                  </div>
                );
              }) : <span />}
            </div>
          ))}
          </div>
        </div>
        <div className="text-xs leading-5 text-[var(--color-text-3)]">
          {term === 'or' ? t('log.event.levelTableOrHint') : t('log.event.levelTableAndHint')}
        </div>
      </div>
      ) : null}
    </div>
  );
};

export default ConditionSelector;
