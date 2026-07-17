import React, { useState, useEffect } from 'react';
import dayjs from 'dayjs';
import TimeSelector from '@/components/time-selector';
import { Form, Input, Select, DatePicker, Switch, InputNumber, Button, Tooltip } from 'antd';
import type { FormInstance } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type {
  DatasourceItem,
  InputOption,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';
import CompactEmptyState from '@/app/ops-analysis/components/compactEmptyState';
import { ParamInputControl } from '@/app/ops-analysis/components/paramInputControl';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  getTimeSelectorDefaultValue,
  getTimeSelectorKey,
  type TimeValue,
} from './paramsConfigTimeRange';

const FormTimeSelector: React.FC<{
  value?: TimeValue;
  disabled?: boolean;
  onChange?: (value: TimeValue) => void;
}> = ({ value, disabled = false, onChange }) => {
  const handleChange = (range: number[], originValue: number | null) => {
    if (originValue === 0 && range.length === 2) {
      const tupleRange: [number, number] = [range[0], range[1]];
      onChange?.(tupleRange);
    } else if (originValue !== null) {
      onChange?.(originValue);
    }
  };

  const defaultValue = getTimeSelectorDefaultValue(value);

  return (
    <div
      className="w-full"
      style={disabled ? { pointerEvents: 'none', opacity: 0.6 } : undefined}
    >
      <TimeSelector
        key={getTimeSelectorKey(value)}
        onlyTimeSelect
        className="w-full"
        defaultValue={defaultValue}
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
  onEditInputConfig?: (param: ParamItem) => void;
  onParamOptionsResolved?: (param: ParamItem, options: InputOption[]) => void;
}

const DataSourceParamsConfig: React.FC<DataSourceParamsConfigProps> = ({
  selectedDataSource,
  readonly = false,
  includeFilterTypes = ['params', 'fixed', 'filter'],
  fieldPrefix = 'params',
  preserveValues = false,
  onEditInputConfig,
  onParamOptionsResolved,
}) => {
  const { t } = useTranslation();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const configParams =
    (Array.isArray(selectedDataSource?.params) ? selectedDataSource.params : []).filter(
      (param: ParamItem) =>
        includeFilterTypes.includes(param.filterType || 'fixed')
    );

  if (configParams.length === 0) {
    return (
      <CompactEmptyState description={t('dashboard.noParamSettings')} />
    );
  }

  const renderParamInput = (param: ParamItem) => {
    const { type = 'string', filterType, options } = param;
    const isDisabled = readonly || filterType === 'fixed';
    const inputConfig = normalizeInputConfig(param);

    const fallbackInput = (() => {
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
    })();

    if (!inputConfig) {
      return fallbackInput;
    }

    return (
      <ParamInputControl
        inputConfig={inputConfig}
        fallback={fallbackInput}
        disabled={isDisabled}
        placeholder={t('common.selectTip')}
        onOptionsResolved={(resolvedOptions) =>
          onParamOptionsResolved?.(param, resolvedOptions)
        }
      />
    );
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
        const showInputConfigButton =
          onEditInputConfig && (param.type || 'string') === 'string' && !readonly;

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
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  justifyContent: isVeryLongText ? 'flex-start' : 'flex-end',
                }}
              >
                <div style={getLabelStyle()} title={labelText}>
                  {labelText}
                </div>
                {showInputConfigButton && (
                  <Tooltip title={t('paramInput.editButton')}>
                    <Button
                      type="text"
                      size="small"
                      icon={<SettingOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        onEditInputConfig!(param);
                      }}
                      className="shrink-0 text-[var(--color-text-2)] hover:text-[var(--color-primary)]"
                    />
                  </Tooltip>
                )}
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
