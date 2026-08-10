import React, { useState, useEffect } from 'react';
import TimeSelector from '@/components/time-selector';
import { Form, Input, Select, DatePicker, InputNumber, Button, Tooltip } from 'antd';
import type { FormInstance } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type {
  DatasourceItem,
  InputOption,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';
import CompactEmptyState from '@/components/compact-empty-state';
import { ParamInputControl } from '@/app/ops-analysis/components/paramInputControl';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import { getDataSourceFormParamInitialValue } from '@/app/ops-analysis/utils/dataSourceFormParams';
import DateRangeSelector from './dateRangeSelector';
import {
  getTimeSelectorDefaultValue,
  getTimeSelectorKey,
  type TimeValue,
} from './paramsConfigTimeRange';

const FormTimeSelector: React.FC<{
  value?: TimeValue | null;
  disabled?: boolean;
  onChange?: (value: TimeValue | null) => void;
}> = ({ value, disabled = false, onChange }) => {
  const handleChange = (range: number[], originValue: number | null) => {
    if (originValue == null) {
      onChange?.(null);
    } else if (originValue === 0 && range.length === 2) {
      const tupleRange: [number, number] = [range[0], range[1]];
      onChange?.(tupleRange);
    } else {
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
        clearable={!disabled}
        className="w-full"
        defaultValue={defaultValue}
        onChange={handleChange}
      />
    </div>
  );
};

const NullableBooleanSelect: React.FC<{
  value?: boolean | null;
  disabled?: boolean;
  yesLabel: string;
  noLabel: string;
  onChange?: (value: boolean | null) => void;
}> = ({ value, disabled = false, yesLabel, noLabel, onChange }) => (
  <Select<number>
    value={value == null ? undefined : value ? 1 : 0}
    disabled={disabled}
    allowClear={!disabled}
    placeholder="--"
    style={{ width: '100%' }}
    options={[
      { label: yesLabel, value: 1 },
      { label: noLabel, value: 0 },
    ]}
    onChange={(nextValue) =>
      onChange?.(nextValue == null ? null : nextValue === 1)
    }
  />
);

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
            allowClear={!isDisabled}
            options={options}
          />
        );
      }

      switch (type) {
        case 'timeRange':
          return <FormTimeSelector disabled={isDisabled} />;
        case 'dateRange':
          return <DateRangeSelector disabled={isDisabled} allowClear className="w-full" />;
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
          return (
            <NullableBooleanSelect
              disabled={isDisabled}
              yesLabel={t('common.yes')}
              noLabel={t('common.no')}
            />
          );
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

  return (
    <>
      {configParams.map((param: ParamItem) => {
        const fieldName = [fieldPrefix, param.name];
        const initialValue = getDataSourceFormParamInitialValue(param);
        const labelText = param.alias_name || param.name;
        const isLongText = labelText.length > 18;
        const isVeryLongText = labelText.length > 30;
        const showInputConfigButton =
          onEditInputConfig &&
          (param.type || 'string') === 'string' &&
          param.filterType !== 'fixed' &&
          !readonly;

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
              textAlign: 'left',
            };
          }
          return {
            ...baseStyle,
            whiteSpace: 'nowrap',
            overflow: 'visible',
            textAlign: 'left',
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
                  justifyContent: 'flex-start',
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
