'use client';

import { useEffect, useRef, useState } from 'react';
import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';
import type { SourceDataResult } from '@/app/ops-analysis/utils/sourceDataResponse';
import type { SourceDataRequestOptions } from '@/app/ops-analysis/api/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  createParamInputOptionsLoader,
  buildParamInputOptionsResultKey,
  getParamInputConfigKey,
  type ParamInputOptionsLoaderOptions,
  type ParamInputOptionsState,
} from '@/app/ops-analysis/utils/paramInputOptionsLoader';

export type UseParamInputOptionsState = ParamInputOptionsState & { resultKey?: string };

interface UseParamInputOptionsRuntime {
  enabled?: boolean;
  getSourceDataByApiId?: (
    id: number,
    params?: unknown,
    options?: SourceDataRequestOptions,
  ) => Promise<SourceDataResult>;
}

export const useParamInputOptions = (
  inputConfig?: InputControlConfig,
  loaderOptions?: ParamInputOptionsLoaderOptions,
  runtime: UseParamInputOptionsRuntime = {},
): UseParamInputOptionsState => {
  const api = useDataSourceApi();
  const apiRef = useRef(api);
  apiRef.current = api;
  const loaderOptionsRef = useRef(loaderOptions);
  loaderOptionsRef.current = loaderOptions;
  const runtimeRef = useRef(runtime);
  runtimeRef.current = runtime;
  const loaderRef = useRef<ReturnType<typeof createParamInputOptionsLoader> | null>(null);
  if (!loaderRef.current) {
    loaderRef.current = createParamInputOptionsLoader(
      {
        getDataSourceList: (...args) => apiRef.current.getDataSourceList(...args),
        getSourceDataByApiId: (...args) =>
          runtimeRef.current.getSourceDataByApiId?.(...args)
          ?? apiRef.current.getSourceDataByApiId(...args),
      },
      () => loaderOptionsRef.current,
    );
  }
  const configRef = useRef(inputConfig);
  configRef.current = inputConfig;
  const enabled = runtime.enabled ?? true;
  const inputKey = getParamInputConfigKey(inputConfig);
  const knownSourcesKey = (loaderOptions?.knownDataSources ?? [])
    .map((item) => `${item.id}:${item.rest_api ?? ''}`)
    .sort()
    .join(',');
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
  const knownSourcesKeyRef = useRef(knownSourcesKey);

  useEffect(() => {
    if (!enabled) {
      if (resolved.key === inputKey && resolved.state.status === 'loading') {
        loaderRef.current!.reset();
      }
      return undefined;
    }
    if (knownSourcesKeyRef.current !== knownSourcesKey) {
      knownSourcesKeyRef.current = knownSourcesKey;
      loaderRef.current!.reset();
    }
    let active = true;
    const load = loaderRef.current!.load(configRef.current);
    setResolved({ key: inputKey, state: load.initial });
    if (!load.sync) {
      void load.promise.then((result) => {
        if (active && result) setResolved({ key: inputKey, state: result });
      });
    }
    return () => {
      active = false;
    };
  }, [enabled, inputKey, knownSourcesKey]);

  const state = resolved.key === inputKey ? resolved.state : getSynchronousState();
  return {
    ...state,
    resultKey: state.status === 'success'
      ? buildParamInputOptionsResultKey(inputKey, state.options)
      : undefined,
  };
};
