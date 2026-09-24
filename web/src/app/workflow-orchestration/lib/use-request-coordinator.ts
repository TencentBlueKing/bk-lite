import { useEffect, useRef } from 'react';

import { createRequestCoordinator, type RequestCoordinator } from './request-coordinator';

export function useRequestCoordinator(setLoading: (loading: boolean) => void) {
  const coordinatorRef = useRef<RequestCoordinator | undefined>(undefined);
  const cleanupTimerRef = useRef<number | undefined>(undefined);
  if (!coordinatorRef.current) coordinatorRef.current = createRequestCoordinator(setLoading);

  useEffect(() => {
    if (cleanupTimerRef.current !== undefined) window.clearTimeout(cleanupTimerRef.current);
    return () => {
      cleanupTimerRef.current = window.setTimeout(() => coordinatorRef.current?.invalidate(), 0);
    };
  }, []);

  return coordinatorRef.current;
}

/** 同一个请求键只自动启动一次，避免 React 严格模式重复初始化。 */
export function useAutoRequest(key: string | undefined, request: () => void | Promise<void>) {
  const requestRef = useRef(request);
  const lastKeyRef = useRef<string | undefined>(undefined);
  requestRef.current = request;

  useEffect(() => {
    if (!key) {
      lastKeyRef.current = undefined;
      return;
    }
    if (lastKeyRef.current === key) return;
    lastKeyRef.current = key;
    void requestRef.current();
  }, [key]);
}
