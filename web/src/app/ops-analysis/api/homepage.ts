import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { HomepagePreferenceState } from '@/app/ops-analysis/utils/homepageDirectoryActions';

export interface HomepageShortcut {
  dashboard_id: number | null;
}

export interface HomepageAccess {
  status: 'ok' | 'missing' | 'org' | 'permission' | string;
  name: string;
  desc: string;
  is_build_in: boolean;
}

export const useHomepageApi = () => {
  const { get, post } = useApiClient();

  const getState = useCallback(
    (config?: { suppressErrorNotification?: boolean }) =>
      get<HomepagePreferenceState>('/operation_analysis/api/homepage/state/', config),
    [get],
  );

  const getShortcut = useCallback(
    () => get<HomepageShortcut>(
      '/operation_analysis/api/homepage/shortcut/',
      { suppressErrorNotification: true },
    ),
    [get],
  );

  const getAccess = useCallback(
    (dashboardId: string | number) => get<HomepageAccess>(
      `/operation_analysis/api/homepage/access/?dashboard_id=${encodeURIComponent(String(dashboardId))}`,
      { suppressErrorNotification: true },
    ),
    [get],
  );

  const applyPersonal = useCallback(
    (data: { action: 'set' | 'clear' | 'pin_workbench'; dashboard_id?: number }) =>
      post<HomepagePreferenceState>('/operation_analysis/api/homepage/personal/', data),
    [post],
  );

  const applyGlobal = useCallback(
    (data: { action: 'set' | 'restore'; dashboard_id?: number }) =>
      post<HomepagePreferenceState>('/operation_analysis/api/homepage/global/', data),
    [post],
  );

  return {
    getState,
    getShortcut,
    getAccess,
    applyPersonal,
    applyGlobal,
  };
};
