'use client';

import React from 'react';
import { Button, Input, Select, Card, Space } from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { ConditionFilterProps } from '@/app/log/types/event';
import { ListItem } from '@/app/log/types';
import { useTranslation } from '@/utils/i18n';
import groupingStyle from '../index.module.scss';
import { cloneDeep } from 'lodash';
import { AggregateFunctionOption, FUNCTION_LIST } from '@/app/log/constants';
import { useConditionList } from '@/app/log/hooks/event';

const { Option } = Select;

const ConditionFilter: React.FC<ConditionFilterProps> = ({
  data = [],
  fields = [],
  onChange
}) => {
  const { t } = useTranslation();
  const conditionList = useConditionList();

  const functionLabel = (item: AggregateFunctionOption) =>
    item.labelKey.startsWith('log.') ? t(item.labelKey) : item.labelKey;

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
    }
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
            const showField = !functionOption || functionOption.needsField;
            return (
              <li
                className={index + 1 === data.length ? '' : 'mb-[10px]'}
                key={index}
              >
                <div className="flex flex-wrap items-center">
                  <Select
                    className="mr-[10px] w-[240px]"
                    placeholder={t('log.event.selectFunction')}
                    showSearch
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
                      <Option value={item.value} key={item.value}>
                        {functionLabel(item)}
                      </Option>
                    ))}
                  </Select>
                  {showField ? (
                    <Select
                      className="mr-[10px] w-[180px]"
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
                  <Select
                    className="mr-[10px] w-[120px]"
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
                  {functionOption?.unitKey ? (
                    <Space.Compact className="mr-[10px] w-[160px]">
                      <Input
                        placeholder={t('log.event.enterThreshold')}
                        value={conditionItem.value}
                        onChange={(e) => handleValueChange(e, index)}
                      />
                      <span className="flex items-center whitespace-nowrap border border-[var(--color-border)] px-2 text-[12px] text-[var(--color-text-3)]">
                        {t(functionOption.unitKey)}
                      </span>
                    </Space.Compact>
                  ) : (
                    <Input
                      className="mr-[10px] w-[160px]"
                      placeholder={t('log.event.enterThreshold')}
                      value={conditionItem.value}
                      onChange={(e) => handleValueChange(e, index)}
                    />
                  )}
                  {!!index && (
                    <Button
                      className="mr-[10px]"
                      icon={<CloseOutlined />}
                      onClick={() => handleDeleteCondition(index)}
                    />
                  )}
                  <Button icon={<PlusOutlined />} onClick={handleAddCondition} />
                </div>
                {conditionItem.func === 'count_delta' ? (
                  <div className="mt-1 text-[12px] text-[var(--color-text-3)]">
                    {t('log.event.countDeltaTip')}
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
