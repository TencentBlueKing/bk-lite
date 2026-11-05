'use client';

import { useEffect, useRef, useState } from 'react';
import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';
import type { SourceDataResult } from '@/app/ops-analysis/utils/sourceDataResponse';
import type { SourceDataRequestOptions } from '@/app/ops-analysis/api/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { isOptionInputControl } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  createParamInputOptionsLoader,
  buildOptionsLoadSignature,
  buildParamInputOptionsResultKey,
  getParamInputConfigKey,
  type ParamInputOptionsLoaderOptions,
  type ParamInputOptionsState,
} from '@/app/ops-analysis/utils/paramInputOptionsLoader';
import { stableStringify } from '@/app/ops-analysis/utils/optionsQueryParamRefs';

export type UseParamInputOptionsState = ParamInputOptionsState & { resultKey?: string };

interface UseParamInputOptionsRuntime {
  enabled?: boolean;
  reloadKey?: string;
  resolvedQueryParams?: Record<string, unknown>;
  optionsBlocked?: boolean;
  optionsBlockReason?: 'empty' | 'invalid';
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
  const reloadKey = runtime.reloadKey ?? '';
  const optionsBlocked = Boolean(runtime.optionsBlocked);
  const optionsBlockReason = runtime.optionsBlockReason;
  const resolvedQueryParams = runtime.resolvedQueryParams;
  const querySignature = stableStringify(resolvedQueryParams ?? {});
  const inputKey = getParamInputConfigKey(inputConfig);
  const loadSignature = buildOptionsLoadSignature(inputConfig, {
    resolvedParams: resolvedQueryParams,
    blocked: optionsBlocked,
    blockReason: optionsBlockReason,
  });
  const knownSourcesKey = (loaderOptions?.knownDataSources ?? [])
    .map((item) => `${item.id}:${item.rest_api ?? ''}`)
    .sort()
    .join(',');
  const getSynchronousState = (): ParamInputOptionsState => {
    if (!isOptionInputControl(inputConfig)) {
      return { status: 'idle', options: [] };
    }
    if (inputConfig.optionsSource.type === 'static') {
      const options = inputConfig.optionsSource.staticItems;
      return options.length ? { status: 'success', options } : { status: 'error', options: [] };
    }
    if (optionsBlocked) return { status: 'blocked', options: [] };
    return { status: 'loading', options: [] };
  };
  const [resolved, setResolved] = useState<{ key: string; state: ParamInputOptionsState }>(() => ({
    key: loadSignature,
    state: getSynchronousState(),
  }));
  const knownSourcesKeyRef = useRef(knownSourcesKey);
  const reloadKeyRef = useRef(reloadKey);
  const reloadChanged = reloadKeyRef.current !== reloadKey;

  useEffect(() => {
    if (!enabled) {
      if (resolved.key === loadSignature && resolved.state.status === 'loading') {
        loaderRef.current!.reset();
      }
      return undefined;
    }
    if (reloadKeyRef.current !== reloadKey) {
      const nextKey = buildOptionsLoadSignature(configRef.current, {
        resolvedParams: runtimeRef.current.resolvedQueryParams,
        blocked: runtimeRef.current.optionsBlocked,
        blockReason: runtimeRef.current.optionsBlockReason,
      });
      reloadKeyRef.current = reloadKey;
      loaderRef.current!.dropSettledCache(nextKey);
    }
    if (knownSourcesKeyRef.current !== knownSourcesKey) {
      knownSourcesKeyRef.current = knownSourcesKey;
      loaderRef.current!.reset();
    }
    let active = true;
    const request = {
      resolvedParams: runtimeRef.current.resolvedQueryParams,
      blocked: runtimeRef.current.optionsBlocked,
      blockReason: runtimeRef.current.optionsBlockReason,
    };
    const load = loaderRef.current!.load(configRef.current, request);
    setResolved({ key: loadSignature, state: load.initial });
    if (!load.sync) {
      void load.promise.then((result) => {
        if (active && result) setResolved({ key: loadSignature, state: result });
      });
    }
    return () => {
      active = false;
    };
  }, [enabled, inputKey, knownSourcesKey, loadSignature, optionsBlockReason, optionsBlocked, querySignature, reloadKey]);

  const state = reloadChanged
    ? { status: 'loading' as const, options: [] as [] }
    : (resolved.key === loadSignature ? resolved.state : getSynchronousState());
  return {
    ...state,
    resultKey: state.status === 'success'
      ? buildParamInputOptionsResultKey(inputKey, state.options)
      : undefined,
  };
};
