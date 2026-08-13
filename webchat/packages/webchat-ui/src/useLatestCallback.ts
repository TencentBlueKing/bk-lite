import { useLayoutEffect, useRef } from 'react';

/** Keep a lifecycle-owned listener pointed at the latest committed callback. */
export function useLatestCallback<T>(callback: T) {
  const callbackRef = useRef(callback);
  useLayoutEffect(() => {
    callbackRef.current = callback;
  }, [callback]);
  return callbackRef;
}
