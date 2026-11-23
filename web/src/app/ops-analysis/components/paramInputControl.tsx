'use client';

import React, { useEffect, useRef } from 'react';
import { Radio, Select, Spin } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import { useParamInputOptions } from '@/app/ops-analysis/hooks/useParamInputOptions';
import {
  createParamInputOptionsNotifier,
  getParamInputConfigKey,
} from '@/app/ops-analysis/utils/paramInputOptionsLoader';
import { normalizeParamInputChangeValue } from '@/app/ops-analysis/components/normalizeParamInputChangeValue';
import ParamInputTableSelect from '@/app/ops-analysis/components/paramInputTableSelect';
import { toSingleOrganizationValue } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';

interface ParamInputControlProps {
  inputConfig?: InputControlConfig;
  fallback: React.ReactNode;
  value?: string | number | Array<string | number>;
  onChange?: (value: string | number | Array<string | number> | null) => void;
  disabled?: boolean;
  placeholder?: string;
  allowClear?: boolean;
  style?: React.CSSProperties;
  onOptionsResolved?: (options: InputOption[]) => void;
  onOptionsFailed?: () => void;
  optionsNotifyKey?: string;
  resolvedQueryParams?: Record<string, unknown>;
  optionsBlocked?: boolean;
  optionsBlockReason?: 'empty' | 'invalid';
  optionsQuerySignature?: string;
  /** 当前用户能否打开组件编辑器修好选项来源。 */
  canRepairOptionSource?: boolean;
  /** 配置表只选择要保存的初始值，不渲染运行时的单选按钮。 */
  valuePicker?: boolean;
}

const emptyUpstreamHint = (
  inputConfig: InputControlConfig,
  translate: (key: string) => string,
) => {
  const classificationHint = translate('dashboard.selectClassificationFirst');
  if (
    inputConfig.control === 'select'
    && inputConfig.optionsSource.type === 'dynamic'
    && inputConfig.optionsSource.emptyUpstreamHintKey === 'dashboard.selectClassificationFirst'
  ) {
    return classificationHint;
  }
  if (
    inputConfig.control === 'select'
    && inputConfig.optionsSource.type === 'dynamic'
    && inputConfig.optionsSource.emptyUpstreamHintKey === 'dashboard.selectMonitorObjectFirst'
  ) {
    return translate('dashboard.selectMonitorObjectFirst');
  }
  return translate('paramInput.dynamic.upstreamRequired');
};

export const ParamInputControl: React.FC<ParamInputControlProps> = ({
  inputConfig,
  fallback,
  value,
  onChange,
  disabled,
  placeholder,
  allowClear = true,
  style,
  onOptionsResolved,
  onOptionsFailed,
  optionsNotifyKey = '',
  resolvedQueryParams,
  optionsBlocked = false,
  optionsBlockReason,
  optionsQuerySignature = '',
  canRepairOptionSource = false,
  valuePicker = false,
}) => {
  const { t } = useTranslation();
  const state = useParamInputOptions(inputConfig, undefined, {
    reloadKey: optionsNotifyKey,
    resolvedQueryParams,
    optionsBlocked,
    optionsBlockReason,
  });
  const onOptionsResolvedRef = useRef(onOptionsResolved);
  const onOptionsFailedRef = useRef(onOptionsFailed);
  const notifierRef = useRef(createParamInputOptionsNotifier());
  const notifyKeyRef = useRef(optionsNotifyKey);
  onOptionsResolvedRef.current = onOptionsResolved;
  onOptionsFailedRef.current = onOptionsFailed;

  const renderFallback = () => {
    if (!React.isValidElement(fallback)) return fallback;
    return React.cloneElement(fallback as React.ReactElement<any>, {
      value,
      onChange: (valueOrEvent: unknown) =>
        onChange?.(normalizeParamInputChangeValue(valueOrEvent)),
      disabled,
    });
  };

  useEffect(() => {
    if (notifyKeyRef.current !== optionsNotifyKey) {
      notifyKeyRef.current = optionsNotifyKey;
      notifierRef.current = createParamInputOptionsNotifier();
    }
    if (state.status === 'error' && state.errorMessage) {
      onOptionsFailedRef.current?.();
      return;
    }
    if (!onOptionsResolvedRef.current) return;
    if (state.status === 'success' && state.resultKey) {
      notifierRef.current.notify(
        state.resultKey,
        state.options,
        onOptionsResolvedRef.current,
      );
      return;
    }
    // 数据源明确返回空列表时也要通知，否则导入来的 ID 会一直挂在控件上。
    if (state.status === 'error' && !state.errorMessage) {
      notifierRef.current.notify(
        `empty:${getParamInputConfigKey(inputConfig)}`,
        [],
        onOptionsResolvedRef.current,
      );
      return;
    }
    if (state.status === 'blocked') {
      notifierRef.current.notify(
        `blocked:${optionsQuerySignature}`,
        [],
        onOptionsResolvedRef.current,
      );
    }
  }, [inputConfig, optionsNotifyKey, optionsQuerySignature, state]);

  if (!inputConfig || inputConfig.control === 'input') return <>{renderFallback()}</>;

  if (inputConfig.control === 'organization') {
    return (
      <GroupTreeSelect
        value={toSingleOrganizationValue(value)}
        onChange={(nextValue) => {
          const scalar = Array.isArray(nextValue) ? nextValue[0] : nextValue;
          onChange?.(scalar ?? null);
        }}
        multiple={false}
        mode="ownership"
        allowClear={allowClear}
        disabled={disabled}
        placeholder={placeholder || ' '}
        style={{ minWidth: 180, ...style }}
      />
    );
  }

  // 筛选栏上的单选没有下拉壳。加载时继续留出宽度，避免把后面的筛项挤开。
  if (state.status === 'loading' && inputConfig.control === 'radio' && !valuePicker) {
    return <Spin size="small" />;
  }

  if (state.status === 'blocked') {
    return (
      <Select
        disabled
        value={undefined}
        placeholder={optionsBlockReason === 'invalid'
          ? t('paramInput.dynamic.invalidUpstream')
          : emptyUpstreamHint(inputConfig, t)}
        style={{ width: '100%', ...style }}
      />
    );
  }

  const sourceIssue = state.status === 'error' ? state.errorMessage : undefined;
  const sourceIssueKeys: Record<string, string> = {
    'option-source-ambiguous': canRepairOptionSource
      ? 'paramInput.dynamic.optionSourceAmbiguous'
      : 'paramInput.dynamic.optionSourceAmbiguousReadonly',
    'option-source-missing': 'paramInput.dynamic.optionSourceMissing',
    'option-source-forbidden': 'paramInput.dynamic.optionSourceForbidden',
    'option-source-unavailable': 'paramInput.dynamic.optionSourceUnavailable',
  };
  const sourceIssueKey = sourceIssue ? (sourceIssueKeys[sourceIssue] ?? '') : '';
  const options = state.status === 'success' ? state.options : [];
  const optionsLoading = state.status === 'loading';
  const sourceLocked = Boolean(sourceIssueKey);

  if (sourceLocked) {
    return (
      <div>
        <Select
          disabled
          value={value}
          style={{ width: '100%', ...style }}
        />
        <div className="mt-1 text-xs text-[var(--color-text-2)]">{t(sourceIssueKey)}</div>
      </div>
    );
  }

  // 配置表里的单选只挑选要保存的初始值，落到下面的可搜索下拉。
  if (inputConfig.control === 'radio' && !valuePicker) {
    return (
      <Radio.Group
        value={value}
        disabled={disabled}
        options={options}
        optionType="button"
        buttonStyle="outline"
        onChange={(event) => onChange?.(event.target.value ?? null)}
      />
    );
  }

  if (inputConfig.control === 'select') {
    const isMultiple = Boolean(inputConfig.multiple);
    if (inputConfig.picker === 'table') {
      return (
        <ParamInputTableSelect
          options={options}
          value={value}
          onChange={onChange}
          disabled={disabled}
          placeholder={placeholder}
          allowClear={allowClear}
          multiple={isMultiple}
          maxCount={isMultiple ? inputConfig.maxCount : undefined}
          loading={optionsLoading}
          style={style}
        />
      );
    }
    return (
      <Select
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        allowClear={allowClear}
        loading={optionsLoading}
        showSearch
        optionFilterProp="label"
        mode={inputConfig.multiple ? 'multiple' : undefined}
        maxCount={isMultiple ? inputConfig.maxCount : undefined}
        maxTagCount={isMultiple ? 'responsive' : undefined}
        maxTagTextLength={isMultiple ? 16 : undefined}
        style={{ width: '100%', ...style }}
        options={options}
        onChange={(nextValue) => onChange?.(nextValue ?? null)}
      />
    );
  }

  return (
    <Select
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      allowClear={allowClear}
      loading={optionsLoading}
      showSearch
      optionFilterProp="label"
      style={{ width: '100%', ...style }}
      options={options}
      onChange={(nextValue) => onChange?.(nextValue ?? null)}
    />
  );
};
