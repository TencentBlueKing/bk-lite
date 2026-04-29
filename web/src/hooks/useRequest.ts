import { useState, useEffect, useCallback, useRef } from 'react';

interface UseRequestOptions<TData, TParams extends unknown[]> {
  manual?: boolean;
  defaultData?: TData;
  refreshDeps?: unknown[];
  onSuccess?: (data: TData, params: TParams) => void;
  onError?: (error: Error, params: TParams) => void;
}

interface UseRequestResult<TData, TParams extends unknown[]> {
  data: TData | undefined;
  loading: boolean;
  error: Error | undefined;
  run: (...params: TParams) => Promise<TData>;
  refresh: () => Promise<TData>;
  cancel: () => void;
}

function useRequest<TData = any, TParams extends unknown[] = []>(
  service: (...args: TParams) => Promise<TData>,
  options?: UseRequestOptions<TData, TParams>,
): UseRequestResult<TData, TParams> {
  const {
    manual = false,
    defaultData,
    refreshDeps = [],
    onSuccess,
    onError,
  } = options || {};

  const [data, setData] = useState<TData | undefined>(defaultData);
  const [loading, setLoading] = useState(!manual);
  const [error, setError] = useState<Error | undefined>();

  const abortControllerRef = useRef<AbortController | null>(null);
  const unmountTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const latestParamsRef = useRef<TParams>([] as unknown as TParams);
  const serviceRef = useRef(service);
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);

  serviceRef.current = service;
  onSuccessRef.current = onSuccess;
  onErrorRef.current = onError;

  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const run = useCallback(async (...params: TParams): Promise<TData> => {
    cancel();

    const controller = new AbortController();
    abortControllerRef.current = controller;
    latestParamsRef.current = params;

    setLoading(true);
    setError(undefined);

    try {
      const result = await serviceRef.current(...params);

      if (controller.signal.aborted) {
        return result;
      }

      if (isMountedRef.current) {
        setData(result);
        setLoading(false);
        onSuccessRef.current?.(result, params);
      }

      return result;
    } catch (err) {
      if (controller.signal.aborted) {
        throw err;
      }

      const error = err instanceof Error ? err : new Error(String(err));

      if (isMountedRef.current) {
        setError(error);
        setLoading(false);
        onErrorRef.current?.(error, params);
      }

      throw error;
    }
  }, [cancel]);

  const refresh = useCallback(async (): Promise<TData> => {
    return run(...latestParamsRef.current);
  }, [run]);

  // Auto mode: fetch on mount
  useEffect(() => {
    if (!manual) {
      run(...([] as unknown as TParams));
    }
  }, [manual]); // eslint-disable-line react-hooks/exhaustive-deps

  // RefreshDeps: re-fetch when dependencies change
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    if (!manual) {
      run(...([] as unknown as TParams));
    }
  }, refreshDeps); // eslint-disable-line react-hooks/exhaustive-deps

  // StrictMode-safe unmount cancel
  useEffect(() => {
    isMountedRef.current = true;

    if (unmountTimerRef.current !== null) {
      clearTimeout(unmountTimerRef.current);
      unmountTimerRef.current = null;
    }

    return () => {
      unmountTimerRef.current = setTimeout(() => {
        isMountedRef.current = false;
        cancel();
      }, 0);
    };
  }, [cancel]);

  return { data, loading, error, run, refresh, cancel };
}

export default useRequest;
