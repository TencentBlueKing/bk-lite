import React from 'react';
import { Select, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ListItem } from '@/app/monitor/types';
import { LEVEL_MAP } from '@/app/monitor/constants';
import { COMPARISON_METHOD } from '@/app/monitor/constants/event';
import strategyStyle from '../index.module.scss';
import { cloneDeep } from 'lodash';

const { Option } = Select;

export interface ThresholdItem {
  level: string;
  method: string;
  value: number | null;
}

interface ThresholdListProps {
  data: ThresholdItem[];
  onChange?: (data: ThresholdItem[]) => void;
}

const ThresholdList: React.FC<ThresholdListProps> = ({
  data = [],
  onChange,
}) => {
  const { t } = useTranslation();

  const handleMethodChange = (value: string, index: number) => {
    const newData = cloneDeep(data);
    newData[index].method = value;
    onChange?.(newData);
  };

  const handleValueChange = (value: number | null, index: number) => {
    const newData = cloneDeep(data);
    newData[index].value = value;
    onChange?.(newData);
  };

  return (
    <>
      {data.map((item, index) => (
        <div
          key={item.level}
          className="bg-[var(--color-bg-1)] border shadow-sm p-3 mt-[10px] w-[800px]"
        >
          <div
            className="flex items-center space-x-4 my-1 font-[800]"
            style={{
              borderLeft: `4px solid ${LEVEL_MAP[item.level]}`,
              paddingLeft: '10px',
            }}
          >
            {t(`monitor.events.${item.level}`)}
          </div>
          <div className="flex items-center">
            <span className="mr-[10px]">
              {t('monitor.events.whenResultIs')}
            </span>
            <Select
              className={strategyStyle.filterLabel}
              style={{ width: '100px' }}
              showSearch
              value={item.method}
              placeholder={t('monitor.events.method')}
              onChange={(val) => handleMethodChange(val, index)}
            >
              {COMPARISON_METHOD.map((method: ListItem) => (
                <Option value={method.value} key={method.value}>
                  {method.label}
                </Option>
              ))}
            </Select>
            <InputNumber
              style={{
                width: '200px',
                borderRadius: '0 6px 6px 0',
              }}
              min={0}
              value={item.value}
              onChange={(val) => handleValueChange(val, index)}
            />
          </div>
        </div>
      ))}
    </>
  );
};

export default ThresholdList;
