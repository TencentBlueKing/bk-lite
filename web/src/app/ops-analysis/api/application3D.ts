import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type {
  Application3DAlarmDetailData,
  Application3DDetailData,
  Application3DMetricSeriesResult,
  Application3DWallData,
} from '@/app/ops-analysis/types/sceneWidget';

export interface Application3DTransport {
  getWall: (
    appliedFilters?: Record<string, string[]>,
    signal?: AbortSignal,
  ) => Promise<Application3DWallData>;
  getApplicationDetail: (
    applicationId: string,
    cursor?: string,
    signal?: AbortSignal,
  ) => Promise<Application3DDetailData>;
  getAlarmDetail: (
    applicationId: string,
    alarmId: string,
    signal?: AbortSignal,
  ) => Promise<Application3DAlarmDetailData>;
  getMetric: (
    applicationId: string,
    alarmId: string,
    signal?: AbortSignal,
  ) => Promise<Application3DMetricSeriesResult>;
}

export const useApplication3DApi = (
  shareSessionId?: string,
): Application3DTransport => {
  const { post } = useApiClient();
  const basePath = shareSessionId
    ? `/operation_analysis/api/dashboard_share/session/${shareSessionId}/application3d`
    : '/operation_analysis/api/scene_widgets/application3d';
  const requestOptions = { suppressErrorNotification: true } as const;

  const getWall = useCallback(
    (appliedFilters?: Record<string, string[]>, signal?: AbortSignal) =>
      post<Application3DWallData>(
        `${basePath}/wall/`,
        appliedFilters ? { applied_filters: appliedFilters } : {},
        { ...requestOptions, signal },
      ),
    [basePath, post],
  );
  const getApplicationDetail = useCallback(
    (applicationId: string, cursor?: string, signal?: AbortSignal) =>
      post<Application3DDetailData>(
        `${basePath}/application_detail/`,
        { application_id: applicationId, ...(cursor ? { cursor } : {}) },
        { ...requestOptions, signal },
      ),
    [basePath, post],
  );
  const getAlarmDetail = useCallback(
    (applicationId: string, alarmId: string, signal?: AbortSignal) =>
      post<Application3DAlarmDetailData>(
        `${basePath}/alarm_detail/`,
        { application_id: applicationId, alarm_id: alarmId },
        { ...requestOptions, signal },
      ),
    [basePath, post],
  );
  const getMetric = useCallback(
    (applicationId: string, alarmId: string, signal?: AbortSignal) =>
      post<Application3DMetricSeriesResult>(
        `${basePath}/metric/`,
        { application_id: applicationId, alarm_id: alarmId },
        { ...requestOptions, signal },
      ),
    [basePath, post],
  );

  return { getWall, getApplicationDetail, getAlarmDetail, getMetric };
};
