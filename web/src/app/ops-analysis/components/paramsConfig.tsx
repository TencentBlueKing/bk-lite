import React, { useState, useEffect } from 'react';
import dayjs from 'dayjs';
import TimeSelector from '@/components/time-selector';
import { Form, Input, Select, DatePicker, Switch, InputNumber } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';

type TimeValue = number | [number, number];

const FormTimeSelector: React.FC<{
  value?: TimeValue;
  disabled?: boolean;
  onChange?: (value: TimeValue) => void;
}> = ({ value, disabled = false, onChange }) => {
  const [selectValue, setSelectValue] = useState<number | [number, number]>(
    value ?? 10080
  );
  const [rangeValue, setRangeValue] = useState<[number, number] | null>(null);

  useEffect(() => {
    if (value !== undefined) {
      if (Array.isArray(value)) {
        setSelectValue(0);
        setRangeValue(value as [number, number]);
      } else {
        setSelectValue(value);
        setRangeValue(null);
      }
    }
  }, [value]);

  const handleChange = (range: number[], originValue: number | null) => {
    if (originValue === 0 && range.length === 2) {
      const tupleRange: [number, number] = [range[0], range[1]];
      setSelectValue(0);
      setRangeValue(tupleRange);
      onChange?.(tupleRange);
    } else if (originValue !== null) {
      setSelectValue(originValue);
      setRangeValue(null);
      onChange?.(originValue);
    }
  };

  const formatRangeValue = (
    value: TimeValue | null
  ): [dayjs.Dayjs, dayjs.Dayjs] | null => {
    if (Array.isArray(value) && value.length === 2) {
      return [dayjs(value[0] as number), dayjs(value[1] as number)];
    }
    return null;
  };

  return (
    <div
      className="w-full"
      style={disabled ? { pointerEvents: 'none', opacity: 0.6 } : undefined}
    >
      <TimeSelector
        onlyTimeSelect
        className="w-full"
        defaultValue={{
          selectValue: typeof selectValue === 'number' ? selectValue : 0,
          rangePickerVaule: formatRangeValue(rangeValue),
        }}
        onChange={handleChange}
      />
    </div>
  );
};

interface DataSourceParamsConfigProps {
  selectedDataSource?: DatasourceItem;
  readonly?: boolean;
  includeFilterTypes?: string[];
  fieldPrefix?: string;
  form?: FormInstance;
  preserveValues?: boolean;
}

const DataSourceParamsConfig: React.FC<DataSourceParamsConfigProps> = ({
  selectedDataSource,
  readonly = false,
  includeFilterTypes = ['params', 'fixed', 'filter'],
  fieldPrefix = 'params',
  preserveValues = false,
}) => {
  const { t } = useTranslation();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const configParams =
    selectedDataSource?.params?.filter((param: ParamItem) =>
      includeFilterTypes.includes(param.filterType || 'fixed')
    ) || [];

  if (configParams.length === 0) {
    return null;
  }

  const renderParamInput = (param: ParamItem) => {
    const { type = 'string', filterType, options } = param;
    const isDisabled = readonly || filterType === 'fixed';

    if (options && options.length > 0) {
      return (
        <Select
          placeholder={t('common.selectTip')}
          style={{ width: '100%' }}
          disabled={isDisabled}
          options={options}
        />
      );
    }

    switch (type) {
      case 'timeRange':
        return <FormTimeSelector disabled={isDisabled} />;
      case 'date':
        return (
          <DatePicker
            showTime
            placeholder={t('common.selectTip')}
            style={{ width: '100%' }}
            format="YYYY-MM-DD HH:mm:ss"
            disabled={isDisabled}
          />
        );
      case 'boolean':
        return <Switch disabled={isDisabled} />;
      case 'number':
        return (
          <InputNumber
            placeholder={t('common.inputTip')}
            style={{ width: '100%' }}
            disabled={isDisabled}
          />
        );
      case 'string':
      default:
        return (
          <Input
            placeholder={t('common.inputTip')}
            style={{ width: '100%' }}
            disabled={isDisabled}
          />
        );
    }
  };

  const getParamInitialValue = (param: ParamItem) => {
    const { type = 'string', value } = param;
    switch (type) {
      case 'boolean':
        return value ?? false;
      case 'number':
        return value ?? 0;
      case 'timeRange':
        return value ?? 10080;
      case 'date':
        if (value && (typeof value === 'string' || typeof value === 'number')) {
          return dayjs(value);
        }
        return null;
      default:
        return value ?? '';
    }
  };

  return (
    <>
      {configParams.map((param: ParamItem) => {
        const fieldName = [fieldPrefix, param.name];
        const initialValue = getParamInitialValue(param);
        const labelText = param.alias_name || param.name;
        const isLongText = labelText.length > 18;
        const isVeryLongText = labelText.length > 30;

        const getLabelStyle = (): React.CSSProperties => {
          const baseStyle = {
            lineHeight: '1.4',
            width: '100%',
          };

          if (isVeryLongText) {
            return {
              ...baseStyle,
              whiteSpace: 'normal',
              wordBreak: 'break-word',
              textAlign: 'left',
            };
          }
          if (isLongText) {
            return {
              ...baseStyle,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              textAlign: 'right',
            };
          }
          return {
            ...baseStyle,
            whiteSpace: 'nowrap',
            overflow: 'visible',
            textAlign: 'right',
          };
        };

        return (
          <Form.Item
            key={`${selectedDataSource?.id || 'default'}-${param.name}`}
            label={
              <div style={getLabelStyle()} title={labelText}>
                {labelText}
              </div>
            }
            name={fieldName}
            initialValue={!preserveValues && mounted ? initialValue : undefined}
            tooltip={param.desc || undefined}
            labelCol={{ span: isVeryLongText ? 24 : 5 }}
            wrapperCol={{ span: isVeryLongText ? 24 : 18 }}
            style={{ marginBottom: isVeryLongText ? 20 : 16 }}
            rules={[
              { required: param.required, message: `请配置${labelText}` },
            ]}
          >
            {renderParamInput(param)}
          </Form.Item>
        );
      })}
    </>
  );
};

export default DataSourceParamsConfig;
