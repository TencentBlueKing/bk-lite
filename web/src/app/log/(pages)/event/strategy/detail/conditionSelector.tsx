'use client';

import React from 'react';
import { Button, Input, Select, Card } from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { ConditionFilterProps } from '@/app/log/types/event';
import { ListItem } from '@/app/log/types';
import { useTranslation } from '@/utils/i18n';
import groupingStyle from '../index.module.scss';
import { cloneDeep } from 'lodash';
import { FUNCTION_LIST } from '@/app/log/constants';
import { useConditionList } from '@/app/log/hooks/event';

const { Option } = Select;

const ConditionFilter: React.FC<ConditionFilterProps> = ({
  data = [],
  fields = [],
  onChange,
}) => {
  const { t } = useTranslation();
  const conditionList = useConditionList();

  const handleConditionChange = (extra: {
    val: string;
    index: number;
    field: 'op' | 'field' | 'func';
  }) => {
    const newData = cloneDeep(data);
    newData[extra.index][extra.field] = extra.val;
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
    <Card className="w-[900px]">
      {data.length ? (
        <ul className={groupingStyle.conditions}>
          {data.map((conditionItem, index) => (
            <li
              style={{
                marginBottom: index + 1 === data.length ? 0 : 10,
              }}
              key={index}
            >
              <Select
                style={{
                  width: 200,
                  marginRight: 10,
                }}
                placeholder={t('log.event.selectFunction')}
                showSearch
                value={conditionItem.func}
                onChange={(val) =>
                  handleConditionChange({
                    val,
                    index,
                    field: 'func',
                  })
                }
              >
                {FUNCTION_LIST.map((item: string) => (
                  <Option value={item} key={item}>
                    {item}
                  </Option>
                ))}
              </Select>
              <Select
                style={{
                  width: 200,
                  marginRight: 10,
                }}
                placeholder={t('log.event.selectField')}
                showSearch
                value={conditionItem.field}
                onChange={(val) =>
                  handleConditionChange({
                    val,
                    index,
                    field: 'field',
                  })
                }
              >
                {fields.map((item: string) => (
                  <Option value={item} key={item}>
                    {item}
                  </Option>
                ))}
              </Select>
              <Select
                style={{
                  width: 128,
                  marginRight: 10,
                }}
                placeholder={t('log.event.selectCriteria')}
                value={conditionItem.op}
                onChange={(val) =>
                  handleConditionChange({
                    val,
                    index,
                    field: 'op',
                  })
                }
              >
                {conditionList.map((item: ListItem) => (
                  <Option value={item.id} key={item.id}>
                    {item.name}
                  </Option>
                ))}
              </Select>
              <Input
                style={{
                  width: 200,
                  marginRight: 10,
                }}
                placeholder={t('log.event.enterThreshold')}
                value={conditionItem.value}
                onChange={(e) => handleValueChange(e, index)}
              />
              {!!index && (
                <Button
                  className="mr-[10px]"
                  icon={<CloseOutlined />}
                  onClick={() => handleDeleteCondition(index)}
                />
              )}
              <Button icon={<PlusOutlined />} onClick={handleAddCondition} />
            </li>
          ))}
        </ul>
      ) : (
        <Button icon={<PlusOutlined />} onClick={handleAddCondition} />
      )}
    </Card>
  );
};

export default ConditionFilter;
