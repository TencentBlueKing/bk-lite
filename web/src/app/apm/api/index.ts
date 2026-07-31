import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type {
  ApmIngestSource,
  ApmIngestSourceInput,
  ApmIngestSourceWithCredential,
  ApmIngestSnippet,
  ApmIngestSnippetInput,
  ApmEvent,
  ApmEventQuery,
  ApmHealth,
  ApmService,
  ApmServiceInstance,
  ApmServiceRed,
  ApmPolicy,
  ApmPolicyInput,
  ApmPolicyQueryResult,
  ApmNotificationChannel,
  ApmTraceDetail,
  ApmTracePage,
  ApmTraceSearchParams,
  CatalogStatus,
} from '@/app/apm/types';

interface InstanceQuery {
  environment?: string;
  status?: CatalogStatus;
  include_archived?: boolean;
}

const useApmApi = () => {
  const { del, get, patch, post, put, isLoading } = useApiClient();

  const getServices = useCallback(
    (params: { environment?: string; include_archived?: boolean } = {}) =>
      get<ApmService[]>('/apm/services/', { params }),
    [get]
  );

  const getService = useCallback(
    (serviceId: string, includeArchived = false) =>
      get<ApmService>(`/apm/services/${serviceId}/`, {
        params: { include_archived: includeArchived },
      }),
    [get]
  );

  const getInstances = useCallback(
    (params: InstanceQuery = {}) => get<ApmServiceInstance[]>('/apm/instances/', { params }),
    [get]
  );

  const getIngestSources = useCallback(() => get<ApmIngestSource[]>('/apm/ingest-sources/'), [get]);

  const createIngestSource = useCallback(
    (payload: ApmIngestSourceInput) =>
      post<ApmIngestSourceWithCredential>('/apm/ingest-sources/', payload),
    [post]
  );

  const rotateIngestSource = useCallback(
    (sourceId: string) =>
      post<ApmIngestSourceWithCredential>(`/apm/ingest-sources/${sourceId}/rotate/`),
    [post]
  );

  const disableIngestSource = useCallback(
    (sourceId: string) => post<ApmIngestSource>(`/apm/ingest-sources/${sourceId}/disable/`),
    [post]
  );

  const setIngestSourceOrganizations = useCallback(
    (sourceId: string, organizationIds: number[]) =>
      put<ApmIngestSource>(`/apm/ingest-sources/${sourceId}/organizations/`, {
        organization_ids: organizationIds,
      }),
    [put]
  );

  const getIngestSnippet = useCallback(
    (sourceId: string, payload: ApmIngestSnippetInput) =>
      post<ApmIngestSnippet>(`/apm/ingest-sources/${sourceId}/snippet/`, payload),
    [post]
  );

  const getHealth = useCallback(() => get<ApmHealth>('/apm/health/'), [get]);

  const getServiceRed = useCallback(
    (serviceId: string, environment: string, startedAt?: string, endedAt?: string) =>
      get<ApmServiceRed>(`/apm/services/${serviceId}/metrics/`, {
        params: { environment, started_at: startedAt, ended_at: endedAt },
      }),
    [get]
  );

  const getTraces = useCallback(
    (params: ApmTraceSearchParams) => get<ApmTracePage>('/apm/traces/', { params }),
    [get]
  );

  const getTrace = useCallback(
    (traceId: string) => get<ApmTraceDetail>(`/apm/traces/${traceId}/`),
    [get]
  );

  const getPolicies = useCallback(() => get<ApmPolicy[]>('/apm/policies/'), [get]);

  const createPolicy = useCallback(
    (payload: ApmPolicyInput) => post<ApmPolicy>('/apm/policies/', payload),
    [post]
  );

  const updatePolicy = useCallback(
    (policyId: string, payload: Partial<ApmPolicyInput>) =>
      patch<ApmPolicy>(`/apm/policies/${policyId}/`, payload),
    [patch]
  );

  const deletePolicy = useCallback(
    (policyId: string) => del(`/apm/policies/${policyId}/`),
    [del]
  );

  const setPolicyEnabled = useCallback(
    (policyId: string, enabled: boolean) =>
      post<ApmPolicy>(`/apm/policies/${policyId}/${enabled ? 'enable' : 'disable'}/`),
    [post]
  );

  const testPolicy = useCallback(
    (policyId: string) => post<ApmPolicyQueryResult>(`/apm/policies/${policyId}/test-query/`),
    [post]
  );

  const getEvents = useCallback(
    (params: ApmEventQuery = {}) => get<ApmEvent[]>('/apm/events/', { params }),
    [get]
  );

  const getNotificationChannels = useCallback(
    () => get<ApmNotificationChannel[]>('/apm/notification-channels/'),
    [get]
  );

  return {
    getServices,
    getService,
    getInstances,
    getIngestSources,
    createIngestSource,
    rotateIngestSource,
    disableIngestSource,
    setIngestSourceOrganizations,
    getIngestSnippet,
    getHealth,
    getServiceRed,
    getTraces,
    getTrace,
    getPolicies,
    createPolicy,
    updatePolicy,
    deletePolicy,
    setPolicyEnabled,
    testPolicy,
    getEvents,
    getNotificationChannels,
    isLoading,
  };
};

export default useApmApi;
