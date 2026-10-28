'use client';

import React from 'react';
import { Button, Input, InputNumber, Radio, Select } from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { ConditionFilterProps } from '@/app/log/types/event';
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
import { useConditionList } from '@/app/log/hooks/event';
import { compareOffsetLimit, presentCompare } from '@/app/log/utils/compareTarget';

const { Option } = Select;

const SYMBOLIC_OPERATORS = new Set(['=', '!=', '>', '<']);

const operatorHasSymbol = (id: ListItem['id']) => SYMBOLIC_OPERATORS.has(String(id));

const ConditionSelector: React.FC<ConditionFilterProps> = ({
  data = [],
  fields = [],
  term,
  onTermChange,
  onChange
}) => {
  const { t } = useTranslation();
  const conditionList = useConditionList();

  const functionName = (item: AggregateFunctionOption) => t(item.labelKey);

  const functionMethod = (item: AggregateFunctionOption) => item.value.toUpperCase();

  const showFunctionMethod = (item: AggregateFunctionOption) =>
    functionName(item).trim().toUpperCase() !== functionMethod(item);

  const functionLabel = (item: AggregateFunctionOption) =>
    showFunctionMethod(item)
      ? `${functionName(item)}（${functionMethod(item)}）`
      : functionName(item);

  const handleConditionChange = (extra: {
    val: string;
    index: number;
    field: 'op' | 'field' | 'func';
  }) => {
    const newData = cloneDeep(data);
    newData[extra.index][extra.field] = extra.val;
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
        {data.map((conditionItem, index) => {
          const functionOption = FUNCTION_LIST.find(
            (item) => item.value === conditionItem.func
          );
          const legacyDelta = conditionItem.func === 'count_delta';
          const showField = !legacyDelta && (!functionOption || functionOption.needsField);
          const presentedCompare = presentCompare(conditionItem.compare);
          const compareKind = presentedCompare.kind || 'absolute';
          const comparable = functionOption ? functionOption.comparable !== false : !legacyDelta;
          const showTarget = comparable && compareKind !== 'absolute';
          const customOffset = presentedCompare.to === 'offset_hours' || presentedCompare.to === 'offset_days';
          const showPercent = compareKind === 'percent';
          const showRatio = functionOption?.needsFilter === true;
          const showUnitSuffix = Boolean(functionOption?.unitKey) || showPercent || showRatio;
          const thresholdAddon = !showUnitSuffix
            ? undefined
            : conditionItem.func === 'count_rate'
              ? t('log.event.countRateUnit')
              : conditionItem.func === 'bytes_rate'
                ? t('log.event.bytesRateUnit')
                : '%';
          return (
            <div
              className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3"
              key={index}
            >
              <div className="flex items-start gap-3">
                <span
                  className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-xs font-semibold text-[var(--color-primary)]"
                  aria-label={t('log.event.conditionIndex', '条件 {index}', { index: index + 1 })}
                >
                  {index + 1}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="w-10 shrink-0 text-[var(--color-text-2)]">
                      {t('log.event.statRow')}
                    </span>
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
                    {showField ? (
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
                    ) : null}
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
                  {comparable ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="w-10 shrink-0 text-[var(--color-text-2)]">
                        {t('log.event.compareRow')}
                      </span>
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
                        }))}
                      />
                      {showTarget ? (
                        <>
                          <span className="text-[var(--color-text-2)]">{t('log.event.compareTo')}</span>
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
                        </>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="w-10 shrink-0 text-[var(--color-text-2)]">
                      {t('log.event.triggerRow')}
                    </span>
                    <span className="text-[var(--color-text-2)]">{t('log.event.whenResult')}</span>
                    <Select
                      style={{ width: 96 }}
                      optionLabelProp="label"
                      placeholder={t('log.event.selectCriteria')}
                      value={conditionItem.op}
                      onChange={(val) =>
                        handleConditionChange({
                          val,
                          index,
                          field: 'op'
                        })
                      }
                    >
                      {conditionList.map((item: ListItem) => (
                        <Option
                          value={item.id}
                          key={item.id}
                          label={operatorHasSymbol(item.id) ? String(item.id) : item.name}
                        >
                          {operatorHasSymbol(item.id) ? `${item.id} ${item.name}` : item.name}
                        </Option>
                      ))}
                    </Select>
                    <Input
                      style={{ width: 140 }}
                      placeholder={t('log.event.enterThreshold')}
                      value={conditionItem.value}
                      onChange={(e) => handleValueChange(e, index)}
                      {...(thresholdAddon ? { addonAfter: thresholdAddon } : {})}
                    />
                  </div>
                  {legacyDelta ? (
                    <div className="text-xs leading-5 text-[var(--color-text-3)]">
                      {t('log.event.countDeltaTip')}
                    </div>
                  ) : null}
                  {showPercent ? (
                    <div className="text-xs leading-5 text-[var(--color-text-3)]">
                      {t('log.event.percentTip')}
                    </div>
                  ) : null}
                  {showRatio ? (
                    <div className="text-xs leading-5 text-[var(--color-text-3)]">
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
      </div>
    </div>
  );
};

export default ConditionSelector;
