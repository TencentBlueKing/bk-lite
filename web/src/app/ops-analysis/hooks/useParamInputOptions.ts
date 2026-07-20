'use client';

import { useEffect, useRef, useState } from 'react';
import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  createParamInputOptionsLoader,
  buildParamInputOptionsResultKey,
  getParamInputConfigKey,
  type ParamInputOptionsState,
} from '@/app/ops-analysis/utils/paramInputOptionsLoader';

export type UseParamInputOptionsState = ParamInputOptionsState & { resultKey?: string };

export const useParamInputOptions = (
  inputConfig?: InputControlConfig,
): UseParamInputOptionsState => {
  const api = useDataSourceApi();
  const apiRef = useRef(api);
  apiRef.current = api;
  const loaderRef = useRef<ReturnType<typeof createParamInputOptionsLoader> | null>(null);
  if (!loaderRef.current) {
    loaderRef.current = createParamInputOptionsLoader({
      getDataSourceList: (...args) => apiRef.current.getDataSourceList(...args),
      getSourceDataByApiId: (...args) => apiRef.current.getSourceDataByApiId(...args),
    });
  }
  const configRef = useRef(inputConfig);
  configRef.current = inputConfig;
  const inputKey = getParamInputConfigKey(inputConfig);
  const getSynchronousState = (): ParamInputOptionsState => {
    if (!inputConfig || inputConfig.control === 'input') return { status: 'idle', options: [] };
    if (inputConfig.optionsSource.type === 'static') {
      const options = inputConfig.optionsSource.staticItems;
      return options.length ? { status: 'success', options } : { status: 'error', options: [] };
    }
    return { status: 'loading', options: [] };
  };
  const [resolved, setResolved] = useState<{ key: string; state: ParamInputOptionsState }>(() => ({
    key: inputKey,
    state: getSynchronousState(),
  }));

  useEffect(() => {
    const load = loaderRef.current!.load(configRef.current);
    setResolved({ key: inputKey, state: load.initial });
    if (!load.sync) {
      void load.promise.then((result) => {
        if (result) setResolved({ key: inputKey, state: result });
      });
    }
  }, [inputKey]);

  const state = resolved.key === inputKey ? resolved.state : getSynchronousState();
  return {
    ...state,
    resultKey: state.status === 'success'
      ? buildParamInputOptionsResultKey(inputKey, state.options)
      : undefined,
  };
};
