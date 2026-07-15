'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Radio, Select, Spin } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  extractDataSourceItems,
  mapDynamicItems,
  resolveDynamicSourceId,
} from '@/app/ops-analysis/utils/paramInputConfigUtils';

interface ParamInputControlProps {
  inputConfig?: InputControlConfig;
  fallback: React.ReactNode;
  value?: string | number;
  onChange?: (value: string | number | null) => void;
  disabled?: boolean;
  placeholder?: string;
  allowClear?: boolean;
  style?: React.CSSProperties;
}

type FetchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; options: InputOption[] }
  | { status: 'error' };

export const ParamInputControl: React.FC<ParamInputControlProps> = ({
  inputConfig,
  fallback,
  value,
  onChange,
  disabled,
  placeholder,
  allowClear = true,
  style,
}) => {
  const { getDataSourceList, getSourceDataByApiId } = useDataSourceApi();
  const requestIdRef = useRef(0);
  const [state, setState] = useState<FetchState>({ status: 'idle' });

  const renderFallback = () => {
    if (!React.isValidElement(fallback)) return fallback;
    return React.cloneElement(fallback as React.ReactElement<any>, {
      value,
      onChange,
      disabled,
    });
  };

  useEffect(() => {
    const requestId = ++requestIdRef.current;

    if (!inputConfig || inputConfig.control === 'input') {
      setState({ status: 'idle' });
      return;
    }

    if (inputConfig.optionsSource.type === 'static') {
      const options = inputConfig.optionsSource.staticItems;
      setState(options.length > 0 ? { status: 'success', options } : { status: 'error' });
      return;
    }

    const source = inputConfig.optionsSource;
    setState({ status: 'loading' });

    const loadOptions = async () => {
      try {
        const dataSources = source.sourceRef
          ? await getDataSourceList({ page_size: -1 })
          : [];
        const sourceItems = Array.isArray(dataSources)
          ? dataSources
          : dataSources?.items || [];
        const sourceId = resolveDynamicSourceId(source, sourceItems);
        if (!sourceId) {
          if (requestId === requestIdRef.current) setState({ status: 'error' });
          return;
        }

        const response = await getSourceDataByApiId(sourceId, {});
        const options = mapDynamicItems(
          extractDataSourceItems(response),
          source.valueField,
          source.labelField,
        );

        if (requestId === requestIdRef.current) {
          setState(options.length > 0 ? { status: 'success', options } : { status: 'error' });
        }
      } catch {
        if (requestId === requestIdRef.current) setState({ status: 'error' });
      }
    };

    loadOptions();
  }, [getDataSourceList, getSourceDataByApiId, inputConfig]);

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
