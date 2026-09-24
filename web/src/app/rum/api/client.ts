'use client';

import { useCallback, useMemo } from 'react';

import useApiClient, { type RequestConfig } from '@/utils/request';

const RUM_API_PREFIX = '/rum';

function rumPath(path: string): string {
  const normalized = (path.startsWith('/') ? path : `/${path}`).replace(/\/{2,}/g, '/');
  // Next.js redirects `/foo/` → `/foo` with 308. The BFF proxy re-adds the
  // Django trailing slash, so the browser URL must not end with `/`.
  return `${RUM_API_PREFIX}${normalized}`.replace(/\/+$/, '') || RUM_API_PREFIX;
}

/**
 * Host adapter over BK-Lite `useApiClient`.
 * Paths are relative to `/api/proxy/rum` (Django `apps.rum` routes).
 * No RUM-specific error suppression — request failures use the shared framework toast.
 * Do not re-render request failures as page Alerts.
 */
export function useRumApi() {
  const { get, post, put, patch, del } = useApiClient();

  const rumGet = useCallback(
    <T = unknown>(path: string, config?: RequestConfig) => get<T>(rumPath(path), config),
    [get],
  );
  const rumPost = useCallback(
    <T = unknown>(path: string, data?: unknown, config?: RequestConfig) =>
      post<T>(rumPath(path), data, config),
    [post],
  );
  const rumPut = useCallback(
    <T = unknown>(path: string, data?: unknown, config?: RequestConfig) =>
      put<T>(rumPath(path), data, config),
    [put],
  );
  const rumPatch = useCallback(
    <T = unknown>(path: string, data?: unknown, config?: RequestConfig) =>
      patch<T>(rumPath(path), data, config),
    [patch],
  );
  const rumDel = useCallback(
    <T = unknown>(path: string, config?: RequestConfig) => del<T>(rumPath(path), config),
    [del],
  );

  return useMemo(
    () => ({
      get: rumGet,
      post: rumPost,
      put: rumPut,
      patch: rumPatch,
      del: rumDel,
      path: rumPath,
    }),
    [rumGet, rumPost, rumPut, rumPatch, rumDel],
  );
}

/** False until the shared API client has a token. Gate list effects on this. */
export function useRumAuthReady(): boolean {
  const { isLoading } = useApiClient();
  return !isLoading;
}

export { rumPath, RUM_API_PREFIX };
