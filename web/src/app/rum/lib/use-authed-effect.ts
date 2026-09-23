'use client';

import { useEffect } from 'react';

/**
 * Run a RUM list/detail fetch only after the shared API client has a token.
 * Ignore in-flight results when the effect is cancelled (Strict Mode / filter change).
 */
export function useRumAuthedEffect(
  authReady: boolean,
  effect: (isCancelled: () => boolean) => void,
  deps: readonly unknown[],
): void {
  useEffect(() => {
    if (!authReady) return undefined;
    let cancelled = false;
    effect(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [authReady, ...deps]);
}
