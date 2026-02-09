import React, { useMemo } from 'react';
import { Select, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ListItem } from '@/app/monitor/types';
import { LEVEL_MAP } from '@/app/monitor/constants';
import {
  COMPARISON_METHOD,
  ENUM_COMPARISON_METHOD
} from '@/app/monitor/constants/event';
import { cloneDeep } from 'lodash';

const { Option } = Select;

export interface ThresholdItem {
  level: string;
  method: string;
  value: number | null;
}

interface EnumOption {
  id: number;
  name: string;
  color?: string;
}

interface ThresholdListProps {
  data: ThresholdItem[];
  onChange?: (data: ThresholdItem[]) => void;
  calculationUnit: string | null;
  onUnitChange: (unit: string) => void;
  unitOptions?: any[];
  isEnumMetric?: boolean;
  enumOptions?: EnumOption[];
}

const ThresholdList: React.FC<ThresholdListProps> = ({
  data = [],
  onChange,
  calculationUnit,
  onUnitChange,
  unitOptions = [],
  isEnumMetric = false,
  enumOptions = []
}) => {
  const { t } = useTranslation();

  // 根据是否为枚举类型选择操作符列表
  const comparisonMethods = useMemo(() => {
    return isEnumMetric ? ENUM_COMPARISON_METHOD : COMPARISON_METHOD;
  }, [isEnumMetric]);

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

  const handleUnitChange = (value: string) => {
    onUnitChange(value);
  };

  // 获取当前选中单位的显示文本
  const getUnitLabel = () => {
    const selectedUnit = unitOptions.find(
      (option) => option.unit_id === calculationUnit
    );
    return selectedUnit?.display_unit || selectedUnit?.unit_name || '';
  };

  return (
    <div className="w-full border border-[var(--color-border-2)] rounded-md p-4 bg-[var(--color-bg-1)] shadow-md">
      {/* 单位选择器在右上角 - 枚举类型不显示 */}
      {!isEnumMetric && (
        <div className="flex justify-end mb-[10px]">
          <span className="mr-[10px] leading-[32px]">{t('common.unit')}:</span>
          <Select
            value={calculationUnit}
            style={{ width: 180 }}
            showSearch
            filterOption={(input, option) =>
              option.label.toLowerCase().includes(input.toLowerCase())
            }
            options={unitOptions.map((option) => ({
              label: option.display_unit || option.unit_name,
              value: option.unit_id
            }))}
            onChange={handleUnitChange}
          />
        </div>
      )}
      {/* 阈值级别列表 */}
      {data.map((item, index) => (
        <div
          key={item.level}
          className="border border-[var(--color-border-2)] rounded-md p-3 mt-[10px] relative overflow-hidden"
        >
          {/* 左边框颜色条 */}
          <div
            className="absolute left-0 top-0 bottom-0 w-[4px]"
            style={{ backgroundColor: LEVEL_MAP[item.level] as string }}
          />
          <div className="pl-[10px]">
            <div className="flex items-center space-x-4 my-1 font-[800]">
              {t(`monitor.events.${item.level}`)}
            </div>
            <div className="flex items-center">
              <span className="mr-[10px]">
                {t('monitor.events.whenResultIs')}
              </span>
              <Select
                style={{ width: '100px', marginRight: '10px' }}
                showSearch
                value={item.method}
                placeholder={t('monitor.events.method')}
                onChange={(val) => handleMethodChange(val, index)}
              >
                {comparisonMethods.map((method: ListItem) => (
                  <Option value={method.value} key={method.value}>
                    {method.label}
                  </Option>
                ))}
              </Select>
              {/* 枚举类型用下拉选择，非枚举类型用数字输入 */}
              {isEnumMetric ? (
                <Select
                  style={{ flex: 1 }}
                  value={item.value}
                  placeholder={t('common.select')}
                  onChange={(val) => handleValueChange(val, index)}
                  allowClear
                >
                  {enumOptions.map((option) => (
                    <Option value={option.id} key={option.id}>
                      {option.name}
                    </Option>
                  ))}
                </Select>
              ) : (
                <InputNumber
                  style={{ flex: 1 }}
                  min={0}
                  value={item.value}
                  addonAfter={getUnitLabel()}
                  onChange={(val) => handleValueChange(val, index)}
                />
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default ThresholdList;
