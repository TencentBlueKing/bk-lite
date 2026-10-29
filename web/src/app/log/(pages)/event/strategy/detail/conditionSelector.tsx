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

const ConditionSelector: React.FC<ConditionFilterProps> = ({
  data = [],
  fields = [],
  term,
  onTermChange,
  onChange
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

  return (
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
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('log.event.conditionSection')}</div>
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
              className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3"
              key={index}
            >
              <div className="flex items-start gap-3">
                <span
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-xs font-semibold text-[var(--color-primary)]"
                  aria-label={t('log.event.conditionIndex', '条件 {index}', { index: index + 1 })}
                >
                  {conditionLetter(index)}
                </span>
                <div className="grid min-w-0 flex-1 grid-cols-[3rem_minmax(0,1fr)] items-center gap-x-2 gap-y-2.5">
                  <span className="text-[var(--color-text-2)]">{t('log.event.statRow')}</span>
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <Select
                      style={{ width: 140 }}
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
                        style={{ width: 88 }}
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
                    {showRatio ? (
                      <>
                        <span className="text-[var(--color-text-2)]">{t('log.event.ratioNumerator')}</span>
                        <Input
                          style={{ width: 220 }}
                          placeholder={t('log.event.ratioFilter')}
                          value={conditionItem.params?.filter}
                          onChange={(event) => handleRatioFilter(event, index)}
                        />
                      </>
                    ) : null}
                  </div>
                  {showField ? (
                    <>
                      <span className="text-[var(--color-text-2)]">{t('log.event.fieldRow')}</span>
                      <Select
                        style={{ width: 160 }}
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
                    </>
                  ) : null}
                  <span className="text-[var(--color-text-2)]">{t('log.event.conditionRole')}</span>
                  <Select
                    style={{ width: 140 }}
                    aria-label={t('log.event.conditionRole')}
                    value={guard ? 'guard' : 'regular'}
                    options={[
                      { value: 'regular', label: t('log.event.roleRegular') },
                      { value: 'guard', label: t('log.event.roleGuard'), disabled: term === 'or' },
                    ]}
                    onChange={(val) => handleRoleChange(val, index)}
                  />
                  {comparable ? (
                    <>
                      <span className="text-[var(--color-text-2)]">{t('log.event.compareRow')}</span>
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <Radio.Group
                        name={`log-policy-condition-compare-${index}`}
                        aria-label={t('log.event.compareKind')}
                        optionType="button"
                        size="small"
                        value={compareKind}
                        onChange={(event) => handleCompareKind(event.target.value, index)}
                        options={COMPARE_KIND_LIST.map((item) => ({
                          value: item.value,
                          label: t(item.labelKey),
                          disabled: guard && item.value !== 'absolute',
                        }))}
                      />
                      </div>
                    </>
                  ) : null}
                  {showTarget ? (
                    <>
                      <span className="text-[var(--color-text-2)]">{t('log.event.compareTo')}</span>
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <Select
                          style={{ width: 120 }}
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
                            style={{ width: 120 }}
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
                    </>
                  ) : null}
                  {guard ? (
                    <>
                      <span className="text-[var(--color-text-2)]">{t('log.event.guardThreshold')}</span>
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <Select
                          style={{ width: 112 }}
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
                            style={{ width: 140 }}
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
                            style={{ width: 140 }}
                            placeholder={t('log.event.enterThreshold')}
                            value={conditionItem.value}
                            onChange={(e) => handleValueChange(e, index)}
                          />
                        )}
                      </div>
                      <div className="col-span-2 text-xs leading-5 text-[var(--color-text-3)]">
                        {t('log.event.guardHint')}
                      </div>
                    </>
                  ) : null}
                  {legacyDelta ? (
                    <div className="col-span-2 text-xs leading-5 text-[var(--color-text-3)]">
                      {t('log.event.countDeltaTip')}
                    </div>
                  ) : null}
                  {showPercent ? (
                    <div className="col-span-2 text-xs leading-5 text-[var(--color-text-3)]">
                      {t('log.event.percentTip')}
                    </div>
                  ) : null}
                  {showRatio ? (
                    <div className="col-span-2 text-xs leading-5 text-[var(--color-text-3)]">
                      {t('log.event.ratioFilterTip')}
                    </div>
                  ) : null}
                </div>
                {data.length > 1 ? (
                  <Button
                    type="text"
                    size="small"
                    icon={<CloseOutlined />}
                    aria-label={t('log.event.deleteCondition')}
                    onClick={() => handleDeleteCondition(index)}
                  />
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
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('log.event.levelSection')}</div>
        <div
          className="overflow-x-auto rounded-md border border-[var(--color-border-2)]"
          aria-label={t('log.event.levelSection')}
        >
          <div
            className="grid min-w-[36rem] items-center gap-2 p-3"
            style={{ gridTemplateColumns: `5.5rem repeat(${Math.max(regularColumns.length, 1)}, minmax(12rem, 1fr))` }}
          >
            <span />
            {regularColumns.length ? regularColumns.map(({ conditionItem, index }) => {
              const option = FUNCTION_LIST.find((item) => item.value === conditionItem.func);
              const unit = columnUnit(conditionItem);
              return (
                <div key={`head-${index}`} className="flex min-w-0 items-baseline gap-2 text-sm">
                  <span className="font-mono font-semibold text-[var(--color-primary)]">{conditionLetter(index)}</span>
                  <span className="truncate text-[var(--color-text-1)]">{option ? functionName(option) : ''}</span>
                  {unit ? <span className="shrink-0 text-[var(--color-text-3)]">{unit}</span> : null}
                </div>
              );
            }) : <span />}
            {DISPLAY_LEVELS.map((level) => (
              <React.Fragment key={level}>
                <span className="text-[var(--color-text-2)]">{levelLabel(level)}</span>
                {regularColumns.length ? regularColumns.map(({ conditionItem, index }) => {
                  const { numericCompare, operatorOptions } = operatorChoices(conditionItem);
                  const slots = displayedThresholdSlots(conditionItem);
                  const useNumber = numericCompare || (conditionItem.op != null && LADDER_OPS.has(String(conditionItem.op)));
                  return (
                    <div key={`${level}-${index}`} className="flex min-w-0 items-center gap-1">
                      <Select
                        style={{ width: 112 }}
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
                          className="min-w-0 flex-1"
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
                          placeholder={t('log.event.enterThreshold')}
                          aria-label={levelLabel(level)}
                          value={slots[level]}
                          onChange={(event) => writeLevelSlot(conditionItem, level, event.target.value, index)}
                        />
                      )}
                    </div>
                  );
                }) : <span />}
              </React.Fragment>
            ))}
          </div>
        </div>
        <div className="text-xs leading-5 text-[var(--color-text-3)]">
          {term === 'or' ? t('log.event.levelTableOrHint') : t('log.event.levelTableAndHint')}
        </div>
      </div>
    </div>
  );
};

export default ConditionSelector;
