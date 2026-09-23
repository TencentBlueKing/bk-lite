'use client';

import { useCallback, useMemo } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import type { RumAnalyticsRange, RumTraffic } from '@/app/rum/lib/degradation';

const RANGE_VALUES = new Set<RumAnalyticsRange>(['1h', '24h', '7d']);

export function parseRumRange(raw: string | null | undefined, fallback: RumAnalyticsRange = '24h'): RumAnalyticsRange {
  const value = (raw || '').trim() as RumAnalyticsRange;
  return RANGE_VALUES.has(value) ? value : fallback;
}

export function parseRumTraffic(raw: string | null | undefined, fallback: RumTraffic = 'visitors'): RumTraffic {
  const value = (raw || '').trim() as RumTraffic;
  if (
    value === 'all' ||
    value === 'automated' ||
    value === 'bot' ||
    value === 'synthetic' ||
    value === 'visitors'
  ) {
    return value;
  }
  return fallback;
}

/** Read/write RUM list filters on the current Next.js URL search string. */
export function useRumSearchParams() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const range = useMemo(
    () => parseRumRange(searchParams.get('range')),
    [searchParams],
  );
  const traffic = useMemo(
    () => parseRumTraffic(searchParams.get('traffic')),
    [searchParams],
  );
  const application = searchParams.get('application') || '';
  const q = searchParams.get('q') || '';

  const setParams = useCallback(
    (patch: Record<string, string | null | undefined>, { replace = true }: { replace?: boolean } = {}) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        const trimmed = value == null ? '' : String(value).trim();
        if (!trimmed) {
          next.delete(key);
        } else {
          next.set(key, trimmed);
        }
      }
      const query = next.toString();
      const href = query ? `${pathname}?${query}` : pathname;
      if (replace) {
        router.replace(href, { scroll: false });
      } else {
        router.push(href, { scroll: false });
      }
    },
    [pathname, router, searchParams],
  );

  const setRange = useCallback(
    (value: RumAnalyticsRange) => setParams({ range: value, page: null }),
    [setParams],
  );
  const setTraffic = useCallback(
    (value: RumTraffic) =>
      setParams({ traffic: value === 'visitors' ? null : value, page: null }),
    [setParams],
  );
  const setApplication = useCallback(
    (value: string) => setParams({ application: value || null, page: null }),
    [setParams],
  );
  const setQuery = useCallback(
    (value: string) => setParams({ q: value || null }),
    [setParams],
  );

  return {
    searchParams,
    range,
    traffic,
    application,
    q,
    setParams,
    setRange,
    setTraffic,
    setApplication,
    setQuery,
  };
}
