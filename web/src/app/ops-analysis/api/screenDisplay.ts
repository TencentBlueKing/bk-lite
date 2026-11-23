import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { shareSingleFlight } from '@/app/ops-analysis/api/dashboardShare';

export type ScreenDisplayGrantState = 'absent' | 'active' | 'paused' | 'expired';

export interface ScreenDisplayGrantDto {
  configured: boolean;
  state: ScreenDisplayGrantState;
  duration_days: number;
  expires_at?: string | null;
  url: string;
}

export const SCREEN_DISPLAY_DURATIONS = [1, 7, 30, 90] as const;

const unwrapProxyPayload = async (response: Response) => {
  const payload = await response.json().catch(() => ({}));
  if (payload && typeof payload === 'object' && 'result' in payload) {
    if (payload.result === false) {
      const reason = payload?.data?.reason || 'invalid';
      const error = new Error(payload.message || 'display grant invalid') as Error & { reason?: string };
      error.reason = reason;
      throw error;
    }
    return payload.data ?? payload;
  }
  if (!response.ok) {
    const error = new Error(payload?.detail || 'display grant invalid') as Error & { reason?: string };
    error.reason = payload?.reason || payload?.data?.reason || 'invalid';
    throw error;
  }
  return payload;
};

export function activateScreenDisplay(token: string) {
  return shareSingleFlight(`display:${token}`, async () => {
    const response = await fetch('/api/proxy/operation_analysis/api/screen_display/activate/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
      credentials: 'include',
    });
    return unwrapProxyPayload(response);
  });
}

export const useScreenDisplayApi = () => {
  const { get, post } = useApiClient();

  const getGrant = useCallback(
    (screenId: string | number): Promise<ScreenDisplayGrantDto> =>
      get(`/operation_analysis/api/screen/${screenId}/display_grant/`, {
        suppressErrorNotification: true,
      }),
    [get],
  );

  const quiet = { suppressErrorNotification: true } as const;

  const createGrant = useCallback(
    (screenId: string | number, durationDays: number) =>
      post(`/operation_analysis/api/screen/${screenId}/display_grant/`, {
        duration_days: durationDays,
      }, quiet),
    [post],
  );

  const pauseGrant = useCallback(
    (screenId: string | number) =>
      post(`/operation_analysis/api/screen/${screenId}/display_grant/pause/`, {}, quiet),
    [post],
  );

  const resumeGrant = useCallback(
    (screenId: string | number) =>
      post(`/operation_analysis/api/screen/${screenId}/display_grant/resume/`, {}, quiet),
    [post],
  );

  const regenerateGrant = useCallback(
    (screenId: string | number, durationDays: number) =>
      post(`/operation_analysis/api/screen/${screenId}/display_grant/regenerate/`, {
        duration_days: durationDays,
      }, quiet),
    [post],
  );

  const getDisplayCanvas = useCallback(
    () => get('/operation_analysis/api/screen_display/current/'),
    [get],
  );

  const queryDisplayDataSource = useCallback(
    (dataSourceId: number, params?: unknown) =>
      post(
        `/operation_analysis/api/screen_display/current/query/${dataSourceId}/`,
        params,
        { suppressErrorNotification: true },
      ),
    [post],
  );

  const getDisplayDataSources = useCallback(
    () => get('/operation_analysis/api/screen_display/current/data_sources/'),
    [get],
  );

  const resolveDisplayOptionSource = useCallback(
    (body: { sourceId?: number; builtinKey?: string; sourceRef?: string }) =>
      post(
        '/operation_analysis/api/screen_display/current/resolve_option_source/',
        {
          sourceId: body.sourceId,
          builtinKey: body.builtinKey,
          sourceRef: body.sourceRef
            ? { type: 'rest_api', value: body.sourceRef }
            : undefined,
        },
        { suppressErrorNotification: true },
      ) as Promise<{ status?: string; id?: number }>,
    [post],
  );

  return {
    getGrant,
    createGrant,
    pauseGrant,
    resumeGrant,
    regenerateGrant,
    getDisplayCanvas,
    queryDisplayDataSource,
    getDisplayDataSources,
    resolveDisplayOptionSource,
  };
};
