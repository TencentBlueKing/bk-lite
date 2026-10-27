'use client';

import React from 'react';
import { Button, Input, Select, Card, Space } from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { ConditionFilterProps } from '@/app/log/types/event';
import { ListItem } from '@/app/log/types';
import { useTranslation } from '@/utils/i18n';
import groupingStyle from '../index.module.scss';
import { cloneDeep } from 'lodash';
import {
  AggregateFunctionOption,
  COMPARE_KIND_LIST,
  COMPARE_TARGET_LIST,
  FUNCTION_LIST,
  QUANTILE_LIST,
} from '@/app/log/constants';
import { useConditionList } from '@/app/log/hooks/event';

const { Option } = Select;

const ConditionFilter: React.FC<ConditionFilterProps> = ({
  data = [],
  fields = [],
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
    const current = newData[index].compare || {};
    if (kind === 'absolute') {
      newData[index].compare = { kind: 'absolute' };
    } else {
      newData[index].compare = current.to ? { kind, to: current.to } : { kind };
    }
    onChange?.(newData);
  };

  const handleCompareTarget = (target: string, index: number) => {
    const newData = cloneDeep(data);
    const kind = newData[index].compare?.kind || 'delta';
    newData[index].compare = { kind, to: target };
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
    <Card className="w-full">
      {data.length ? (
        <ul className={groupingStyle.conditions}>
          {data.map((conditionItem, index) => {
            const functionOption = FUNCTION_LIST.find(
              (item) => item.value === conditionItem.func
            );
            const legacyDelta = conditionItem.func === 'count_delta';
            const showField = !legacyDelta && (!functionOption || functionOption.needsField);
            const compareKind = conditionItem.compare?.kind || 'absolute';
            const comparable = functionOption ? functionOption.comparable !== false : !legacyDelta;
            const kindOptions = comparable
              ? COMPARE_KIND_LIST
              : COMPARE_KIND_LIST.filter((item) => item.value === 'absolute');
            const showTarget = comparable && compareKind !== 'absolute';
            const showPercent = compareKind === 'percent';
            const showRatio = functionOption?.needsFilter === true;
            const showUnitSuffix = Boolean(functionOption?.unitKey) || showPercent || showRatio;
            return (
              <li className="w-full" key={index}>
                <div className="flex w-full flex-wrap items-center gap-2">
                  <Select
                    style={{ width: 216 }}
                    popupMatchSelectWidth={false}
                    placeholder={t('log.event.selectFunction')}
                    showSearch
                    optionLabelProp="label"
                    optionFilterProp="label"
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
                      <Option value={item.value} key={item.value} label={functionLabel(item)}>
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
                      style={{ width: 116 }}
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
                      style={{ width: 100 }}
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
                    <Input
                      style={{ width: 180 }}
                      placeholder={t('log.event.ratioFilter')}
                      value={conditionItem.params?.filter}
                      onChange={(event) => handleRatioFilter(event, index)}
                    />
                  ) : null}
                  <Select
                    style={{ width: 120 }}
                    placeholder={t('log.event.compareKind')}
                    value={compareKind}
                    onChange={(val) => handleCompareKind(val, index)}
                  >
                    {kindOptions.map((item) => (
                      <Option value={item.value} key={item.value}>
                        {t(item.labelKey)}
                      </Option>
                    ))}
                  </Select>
                  {showTarget ? (
                    <Select
                      style={{ width: 140 }}
                      placeholder={t('log.event.compareTo')}
                      value={conditionItem.compare?.to}
                      onChange={(val) => handleCompareTarget(val, index)}
                    >
                      {COMPARE_TARGET_LIST.map((item) => (
                        <Option value={item.value} key={item.value}>
                          {t(item.labelKey)}
                        </Option>
                      ))}
                    </Select>
                  ) : null}
                  <Select
                    style={{ width: 112 }}
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
                      <Option value={item.id} key={item.id}>
                        {item.name}
                      </Option>
                    ))}
                  </Select>
                  {showUnitSuffix ? (
                    <Space.Compact style={{ width: 148 }}>
                      <Input
                        placeholder={t('log.event.enterThreshold')}
                        value={conditionItem.value}
                        onChange={(e) => handleValueChange(e, index)}
                      />
                      <span className="flex items-center whitespace-nowrap border border-[var(--color-border)] px-2 text-[12px] text-[var(--color-text-3)]">
                        {showPercent || showRatio ? '%' : t(functionOption?.unitKey || '')}
                      </span>
                    </Space.Compact>
                  ) : (
                    <Input
                      style={{ width: 100 }}
                      placeholder={t('log.event.enterThreshold')}
                      value={conditionItem.value}
                      onChange={(e) => handleValueChange(e, index)}
                    />
                  )}
                  {!!index && (
                    <Button
                      icon={<CloseOutlined />}
                      onClick={() => handleDeleteCondition(index)}
                    />
                  )}
                  <Button icon={<PlusOutlined />} onClick={handleAddCondition} />
                </div>
                {legacyDelta ? (
                  <div className="mt-1 w-full text-[12px] text-[var(--color-text-3)]">
                    {t('log.event.countDeltaTip')}
                  </div>
                ) : null}
                {showPercent ? (
                  <div className="mt-1 w-full text-[12px] text-[var(--color-text-3)]">
                    {t('log.event.percentTip')}
                  </div>
                ) : null}
                {showRatio ? (
                  <div className="mt-1 w-full text-[12px] text-[var(--color-text-3)]">
                    {t('log.event.ratioFilterTip')}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <Button icon={<PlusOutlined />} onClick={handleAddCondition} />
      )}
    </Card>
  );
};

export default ConditionFilter;
