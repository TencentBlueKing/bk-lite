import { useCallback, useMemo } from 'react';
import useApiClient from '@/utils/request';
import type {
  CustomReportingBatchActivityResponse,
  CustomReportingCreateTaskPayload,
  CustomReportingCredentialResponse,
  CustomReportingCredentialRevokeResponse,
  CustomReportingOnboardingDocument,
  CustomReportingTask,
  CustomReportingTaskDetail,
  CustomReportingTaskListResponse,
  CustomReportingUpdateTaskPayload,
} from '@/app/cmdb/types/customReporting';

const CUSTOM_REPORTING_BASE = '/cmdb/api/custom_reporting/tasks';

export const useCustomReportingApi = () => {
  const { get, post, put, del } = useApiClient();

  const getTaskList = useCallback(
    (params?: Record<string, any>) =>
      get<CustomReportingTaskListResponse>(`${CUSTOM_REPORTING_BASE}/`, { params }),
    [get],
  );

  const getTaskDetail = useCallback(
    (taskId: number | string) =>
      get<CustomReportingTaskDetail>(`${CUSTOM_REPORTING_BASE}/${taskId}/`),
    [get],
  );

  const getTaskBatchActivity = useCallback(
    (taskId: number | string) =>
      get<CustomReportingBatchActivityResponse>(
        `${CUSTOM_REPORTING_BASE}/${taskId}/batch_activity/`,
      ),
    [get],
  );

  const createTask = useCallback(
    (params: CustomReportingCreateTaskPayload) =>
      post<CustomReportingTask>(`${CUSTOM_REPORTING_BASE}/`, params),
    [post],
  );

  const updateTask = useCallback(
    (
      taskId: number | string,
      params: CustomReportingUpdateTaskPayload,
    ) => put<CustomReportingTask>(`${CUSTOM_REPORTING_BASE}/${taskId}/`, params),
    [put],
  );

  const deleteTask = useCallback(
    (taskId: number | string) => del(`${CUSTOM_REPORTING_BASE}/${taskId}/`),
    [del],
  );

  const getOnboardingDocument = useCallback(
    (taskId: number | string) =>
      get<CustomReportingOnboardingDocument>(
        `${CUSTOM_REPORTING_BASE}/${taskId}/onboarding_document/`,
      ),
    [get],
  );

  const issueCredential = useCallback(
    (
      taskId: number | string,
      params?: { name?: string },
    ) =>
      post<CustomReportingCredentialResponse>(
        `${CUSTOM_REPORTING_BASE}/${taskId}/issue_credential/`,
        params || {},
      ),
    [post],
  );

  const rotateCredential = useCallback(
    (
      taskId: number | string,
      credentialId: number,
    ) =>
      post<CustomReportingCredentialResponse>(
        `${CUSTOM_REPORTING_BASE}/${taskId}/rotate_credential/`,
        { credential_id: credentialId },
      ),
    [post],
  );

  const revokeCredential = useCallback(
    (
      taskId: number | string,
      credentialId: number,
    ) =>
      post<CustomReportingCredentialRevokeResponse>(
        `${CUSTOM_REPORTING_BASE}/${taskId}/revoke_credential/`,
        { credential_id: credentialId },
      ),
    [post],
  );

  return useMemo(
    () => ({
      getTaskList,
      getTaskDetail,
      getTaskBatchActivity,
      createTask,
      updateTask,
      deleteTask,
      getOnboardingDocument,
      issueCredential,
      rotateCredential,
      revokeCredential,
      supportsBatchQueries: true,
      supportsReviewQueries: true,
    }),
    [
      createTask,
      deleteTask,
      getOnboardingDocument,
      getTaskBatchActivity,
      getTaskDetail,
      getTaskList,
      issueCredential,
      rotateCredential,
      revokeCredential,
      updateTask,
    ],
  );
};
