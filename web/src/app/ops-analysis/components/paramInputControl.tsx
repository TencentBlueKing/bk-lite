'use client';

import React, { useEffect, useRef } from 'react';
import { Radio, Select, Spin } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import { useParamInputOptions } from '@/app/ops-analysis/hooks/useParamInputOptions';
import { createParamInputOptionsNotifier } from '@/app/ops-analysis/utils/paramInputOptionsLoader';
import { normalizeParamInputChangeValue } from '@/app/ops-analysis/components/normalizeParamInputChangeValue';

interface ParamInputControlProps {
  inputConfig?: InputControlConfig;
  fallback: React.ReactNode;
  value?: string | number;
  onChange?: (value: string | number | null) => void;
  disabled?: boolean;
  placeholder?: string;
  allowClear?: boolean;
  style?: React.CSSProperties;
  onOptionsResolved?: (options: InputOption[]) => void;
}

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
}) => {
  const state = useParamInputOptions(inputConfig);
  const onOptionsResolvedRef = useRef(onOptionsResolved);
  const notifierRef = useRef(createParamInputOptionsNotifier());
  onOptionsResolvedRef.current = onOptionsResolved;

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
    if (state.status !== 'success' || !onOptionsResolvedRef.current) return;
    if (!state.resultKey) return;
    notifierRef.current.notify(
      state.resultKey,
      state.options,
      onOptionsResolvedRef.current,
    );
  }, [state]);

  if (!inputConfig || inputConfig.control === 'input') return <>{renderFallback()}</>;
  if (state.status === 'loading') return <Spin size="small" />;
  if (state.status !== 'success' || state.options.length === 0) return <>{renderFallback()}</>;

  if (inputConfig.control === 'radio') {
    return (
      <Radio.Group
        value={value}
        disabled={disabled}
        options={state.options}
        optionType="button"
        buttonStyle="outline"
        onChange={(event) => onChange?.(event.target.value ?? null)}
      />
    );
  }

  return (
    <Select
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      allowClear={allowClear}
      style={{ width: '100%', ...style }}
      options={state.options}
      onChange={(nextValue) => onChange?.(nextValue ?? null)}
    />
  );
};
