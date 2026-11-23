import React, { useState, useEffect, useMemo } from 'react';
import { useDebouncedOptionsQueryValues } from '@/app/ops-analysis/hooks/useDebouncedOptionsQueryValues';
import { isFreeTextOptionsParam } from '@/app/ops-analysis/utils/optionsQueryTextDebounce';
import TimeSelector from '@/components/time-selector';
import { Form, Input, Select, DatePicker, InputNumber, Tooltip } from 'antd';
import type { FormInstance } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type {
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  DatasourceItem,
  InputControlConfig,
  InputOption,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';
import CompactEmptyState from '@/components/compact-empty-state';
import { ParamInputControl } from '@/app/ops-analysis/components/paramInputControl';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import { getDataSourceFormParamInitialValue } from '@/app/ops-analysis/utils/dataSourceFormParams';
import { useDataVariableRuntime } from '@/app/ops-analysis/context/dataVariableRuntime';
import {
  isDataVariableRef,
  substituteDataVariableUpstream,
  type ColumnResult,
  type DataVariable,
} from '@/app/ops-analysis/utils/dataVariable';
import { readComponentOptionsQueryUpstream } from '@/app/ops-analysis/utils/optionsQueryCandidates';
import {
  dynamicQueryParamsOf,
  resolveOptionsQueryParams,
  stableStringify,
  type ResolvedOptionsQuery,
} from '@/app/ops-analysis/utils/optionsQueryParamRefs';
import ConditionFilterControl from '@/app/ops-analysis/components/conditionFilterControl';
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
    className="w-full"
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
  /** 传入后按组件配置表单解析选项查询引用；缺省则保持原请求。 */
  globalFilters?: UnifiedFilterDefinition[];
  filterBindings?: FilterBindings | null;
  globalFilterValues?: Record<string, FilterValue>;
  onEditInputConfig?: (param: ParamItem) => void;
  onParamOptionsResolved?: (param: ParamItem, options: InputOption[]) => void;
  /** 当前用户能否修好选项来源。文案不授予保存权限。 */
  canRepairOptionSource?: boolean;
  /** 用来回显「数据变量 · 名称」。引用本身在参数输入设置里选。 */
  dataVariables?: DataVariable[];
}

const DataVariableEcho: React.FC<{
  value?: unknown;
  variables?: DataVariable[];
}> = ({ value, variables }) => {
  const { t } = useTranslation();
  const id = isDataVariableRef(value) ? value.dataVariableId : '';
  const name = variables?.find((item) => item.id === id)?.name || id;
  return (
    <Input
      disabled
      value={t('dataVariable.referenceLabel', '数据变量 · {name}', { name })}
    />
  );
};

const formParamValue = (
  formParams: Record<string, unknown> | undefined,
  name: string,
  fallback: ParamItem['value'],
) => (
  formParams && Object.prototype.hasOwnProperty.call(formParams, name)
    ? formParams[name]
    : fallback
);

const resolveParamOptionsQuery = ({
  inputConfig,
  enabled,
  formParams,
  sourceParams,
  globalFilters,
  filterBindings,
  globalFilterValues,
  dataVariableColumns,
}: {
  inputConfig?: InputControlConfig;
  enabled: boolean;
  formParams: Record<string, unknown> | undefined;
  sourceParams: ParamItem[];
  globalFilters?: UnifiedFilterDefinition[];
  filterBindings?: FilterBindings | null;
  globalFilterValues?: Record<string, FilterValue>;
  dataVariableColumns?: Record<string, ColumnResult>;
}): { resolution: ResolvedOptionsQuery; signature: string } | undefined => {
  if (!enabled) return undefined;
  const resolution = resolveOptionsQueryParams(
    dynamicQueryParamsOf(inputConfig),
    (ref) => substituteDataVariableUpstream(readComponentOptionsQueryUpstream({
      ref,
      componentParams: sourceParams.map((param) => ({
        name: param.name,
        type: param.type,
        filterType: param.filterType,
        inputConfig: param.inputConfig,
        inputMode: param.inputMode,
        value: formParamValue(formParams, param.name, param.value),
      })),
      definitions: globalFilters ?? [],
      filterBindings,
      readFilterValue: (id) => (
        globalFilterValues && Object.prototype.hasOwnProperty.call(globalFilterValues, id)
          ? globalFilterValues[id]
          : undefined
      ),
    }), dataVariableColumns),
  );
  return {
    resolution,
    signature: stableStringify({
      blocked: resolution.blocked,
      blockReason: resolution.blockReason ?? null,
      params: resolution.params,
    }),
  };
};

const DataSourceParamsConfig: React.FC<DataSourceParamsConfigProps> = ({
  selectedDataSource,
  readonly = false,
  includeFilterTypes = ['params', 'fixed', 'filter'],
  fieldPrefix = 'params',
  preserveValues = false,
  globalFilters,
  filterBindings,
  globalFilterValues,
  onEditInputConfig,
  onParamOptionsResolved,
  canRepairOptionSource = false,
  dataVariables,
}) => {
  const { t } = useTranslation();
  const [mounted, setMounted] = useState(false);
  const dataVariableColumns = useDataVariableRuntime()?.columns;
  const form = Form.useFormInstance();
  // useWatch 负责在未注册字段变化时重渲染；当次渲染读 store，避免订阅值晚一拍。
  const watchedParams = Form.useWatch(fieldPrefix, { form, preserve: true }) as Record<string, unknown> | undefined;
  const storedParams = form.getFieldsValue(true)?.[fieldPrefix] as Record<string, unknown> | undefined;
  const formParams = storedParams ?? watchedParams;
  const resolveOptionsQuery = globalFilters !== undefined;

  useEffect(() => {
    setMounted(true);
  }, []);

  const sourceParams = useMemo(
    () => (Array.isArray(selectedDataSource?.params) ? selectedDataSource.params : []),
    [selectedDataSource?.params],
  );
  const typedParamNames = useMemo(
    () => sourceParams.filter(isFreeTextOptionsParam).map((param) => param.name),
    [sourceParams],
  );
  // 表单控件仍读 form 的即时值。选项查询只吃防抖后的文本/数字。
  const optionsQueryFormParams = useDebouncedOptionsQueryValues(formParams ?? {}, typedParamNames);
  const configParams = sourceParams.filter(
    (param: ParamItem) => includeFilterTypes.includes(param.filterType || 'fixed'),
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
            className="w-full"
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
              className="w-full"
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
              className="w-full"
              disabled={isDisabled}
            />
          );
        case 'string':
        default:
          if (param.name === 'query') {
            return (
              <Input.TextArea
                rows={4}
                placeholder={t('common.inputTip')}
                className="w-full"
                disabled={isDisabled}
              />
            );
          }
          return (
            <Input
              placeholder={t('common.inputTip')}
              className="w-full"
              disabled={isDisabled}
            />
          );
      }
    })();

    if (inputConfig?.control === 'conditionFilter') {
      const fieldQuery = inputConfig.fields.kind === 'dynamic'
        ? resolveParamOptionsQuery({
          inputConfig,
          enabled: resolveOptionsQuery,
          formParams: optionsQueryFormParams,
          sourceParams,
          globalFilters,
          filterBindings,
          globalFilterValues,
          dataVariableColumns,
        })
        : undefined;
      return (
        <ConditionFilterControl
          source={inputConfig.fields}
          formParams={formParams}
          resolvedFieldQuery={fieldQuery?.resolution}
          fieldQuerySignature={fieldQuery?.signature}
          disabled={isDisabled}
          canRepairOptionSource={canRepairOptionSource}
        />
      );
    }

    if (!inputConfig) {
      return fallbackInput;
    }
    if (
      inputConfig.control !== 'select'
      && inputConfig.control !== 'radio'
      && inputConfig.control !== 'input'
      && inputConfig.control !== 'organization'
    ) {
      return fallbackInput;
    }

    const optionsQuery = resolveParamOptionsQuery({
      inputConfig,
      enabled: resolveOptionsQuery,
      formParams: optionsQueryFormParams,
      sourceParams,
      globalFilters,
      filterBindings,
      globalFilterValues,
      dataVariableColumns,
    });

    return (
      <ParamInputControl
        inputConfig={inputConfig}
        fallback={fallbackInput}
        disabled={isDisabled}
        placeholder={t('common.selectTip')}
        resolvedQueryParams={optionsQuery?.resolution.params}
        optionsBlocked={optionsQuery?.resolution.blocked}
        optionsBlockReason={optionsQuery?.resolution.blockReason}
        optionsQuerySignature={optionsQuery?.signature}
        canRepairOptionSource={canRepairOptionSource}
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
        const isVeryLongText = labelText.length > 30;
        const isConditionFilter = param.type === 'conditionFilter'
          || param.inputConfig?.control === 'conditionFilter';
        const showInputConfigButton =
          onEditInputConfig &&
          ((param.type || 'string') === 'string' || isConditionFilter) &&
          param.filterType !== 'fixed' &&
          !readonly;
        const variableValue = isDataVariableRef(formParams?.[param.name]);

        return (
          <Form.Item
            key={`${selectedDataSource?.id || 'default'}-${param.name}`}
            className="[&_.ant-form-item-label>label]:flex [&_.ant-form-item-label>label]:h-auto [&_.ant-form-item-label>label]:w-full"
            label={
              <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-1">
                  <span
                    className={isVeryLongText
                      ? 'min-w-0 whitespace-normal break-words text-left leading-snug'
                      : 'min-w-0 truncate text-left leading-snug'}
                    title={labelText}
                  >
                    {labelText}
                  </span>
                  {param.desc ? (
                    <Tooltip title={param.desc}>
                      <QuestionCircleOutlined className="shrink-0 cursor-help text-sm text-(--color-text-3)" />
                    </Tooltip>
                  ) : null}
                </span>
                {showInputConfigButton && (
                  <button
                    type="button"
                    className="shrink-0 cursor-pointer border-0 bg-transparent p-0 text-sm leading-5 text-(--color-primary)"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      onEditInputConfig!(param);
                    }}
                  >
                    {t('paramInput.editButton')}
                  </button>
                )}
              </div>
            }
            name={fieldName}
            preserve
            initialValue={!preserveValues && mounted ? initialValue : undefined}
            style={{ marginBottom: isVeryLongText ? 20 : 16 }}
            required={Boolean(param.required)}
            rules={variableValue
              ? []
              : [
                { required: param.required, message: t('dataSource.paramRequired', '请配置{label}', { label: labelText }) },
              ]}
          >
            {variableValue ? (
              <DataVariableEcho variables={dataVariables} />
            ) : renderParamInput(param)}
          </Form.Item>
        );
      })}
    </>
  );
};

export default DataSourceParamsConfig;
