'use client';

import { useCallback, useMemo, useRef } from 'react';

export interface LoadSequence {
  /** Start a new load and return its token. Every previously issued token is now stale. */
  begin: () => number;
  /** True only when `token` is the most recently issued one — i.e. this load was not superseded. */
  isCurrent: (token: number) => boolean;
}

/**
 * Monotonic load-sequence guard for async metric loading.
 *
 * Dashboards fire overlapping loads (instance switch, time-range change, silent
 * refresh). Late-arriving results from a superseded load must be discarded so
 * stale data never overwrites fresh data. Call `begin()` at the start of a load,
 * then guard every async continuation with `isCurrent(token)` before committing
 * state. Centralizing this avoids the same off-by-one stale-guard being
 * re-implemented (and drifting) in every bespoke dashboard.
 */
export function useLoadSequence(): LoadSequence {
  const ref = useRef(0);
  const begin = useCallback(() => {
    ref.current += 1;
    return ref.current;
  }, []);
  const isCurrent = useCallback((token: number) => ref.current === token, []);
  return useMemo(() => ({ begin, isCurrent }), [begin, isCurrent]);
}
