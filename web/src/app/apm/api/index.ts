import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { RequestConfig } from '@/utils/request';
import type {
  ApmApplication,
  ApmApplicationInput,
  ApmCloudRegion,
  ApmIngestSnippet,
  ApmIngestSnippetInput,
  ApmEvent,
  ApmEventQuery,
  ApmHealth,
  ApmService,
  ApmServiceInstance,
  ApmServiceRed,
  ApmSlo,
  ApmSloInput,
  ApmPolicy,
  ApmPolicyInput,
  ApmPolicyQueryResult,
  ApmPage,
  ApmNotificationChannel,
  ApmNotificationDelivery,
  ApmNotificationRecipient,
  ApmTraceDetail,
  ApmTracePage,
  ApmTraceSearchParams,
  ApmTopologyGraph,
  CatalogStatus,
} from '@/app/apm/types';

interface InstanceQuery {
  application?: string;
  environment?: string;
  status?: CatalogStatus;
  include_archived?: boolean;
  started_at?: string;
  ended_at?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
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

  const getInstancePage = useCallback(
    (params: InstanceQuery) => get<ApmPage<ApmServiceInstance>>('/apm/instances/', { params }),
    [get]
  );

  const setInstanceOrganizations = useCallback(
    (instanceId: string, organizationIds: number[]) =>
      put<ApmServiceInstance>(`/apm/instances/${instanceId}/organizations/`, {
        organization_ids: organizationIds,
      }),
    [put]
  );

  const setInstanceArchived = useCallback(
    (instanceId: string, archived: boolean) =>
      post<ApmServiceInstance>(`/apm/instances/${instanceId}/${archived ? 'archive' : 'restore'}/`, {
        reason: 'manual',
      }),
    [post]
  );

  const setServiceOrganizations = useCallback(
    (serviceId: string, organizationIds: number[]) =>
      put<ApmService>(`/apm/services/${serviceId}/organizations/`, {
        organization_ids: organizationIds,
      }),
    [put]
  );

  const setServiceArchived = useCallback(
    (serviceId: string, archived: boolean) =>
      post<ApmService>(`/apm/services/${serviceId}/${archived ? 'archive' : 'restore'}/`, {
        reason: 'manual',
      }),
    [post]
  );

  const getApplications = useCallback(
    (config: RequestConfig = {}) => get<ApmApplication[]>('/apm/applications/', config),
    [get]
  );

  const getCloudRegions = useCallback(
    (config: RequestConfig = {}) => get<ApmCloudRegion[]>('/apm/integration-config/regions/', config),
    [get]
  );

  const createApplication = useCallback(
    (payload: ApmApplicationInput) => post<ApmApplication>('/apm/applications/', payload),
    [post]
  );

  const updateApplication = useCallback(
    (applicationId: string, payload: ApmApplicationInput) =>
      put<ApmApplication>(`/apm/applications/${applicationId}/`, payload),
    [put]
  );

  const getIngestSnippet = useCallback(
    (payload: ApmIngestSnippetInput) => post<ApmIngestSnippet>(
      '/apm/integration-config/',
      payload,
      { suppressErrorNotification: true }
    ),
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

  const getSlos = useCallback(() => get<ApmSlo[]>('/apm/slos/'), [get]);

  const createSlo = useCallback(
    (payload: ApmSloInput) => post<ApmSlo>('/apm/slos/', payload),
    [post]
  );

  const updateSlo = useCallback(
    (sloId: string, payload: Partial<ApmSloInput>) => patch<ApmSlo>(`/apm/slos/${sloId}/`, payload),
    [patch]
  );

  const deleteSlo = useCallback((sloId: string) => del(`/apm/slos/${sloId}/`), [del]);

  const setSloEnabled = useCallback(
    (sloId: string, enabled: boolean) => post<ApmSlo>(`/apm/slos/${sloId}/${enabled ? 'enable' : 'disable'}/`),
    [post]
  );

  const getTraces = useCallback(
    (params: ApmTraceSearchParams) => get<ApmTracePage>('/apm/traces/', { params }),
    [get]
  );

  const getTrace = useCallback(
    (traceId: string) => get<ApmTraceDetail>(`/apm/traces/${traceId}/`),
    [get]
  );

  const getTopology = useCallback(
    (params: { started_at: string; ended_at: string; environment?: string }) =>
      get<ApmTopologyGraph>('/apm/topology/', { params }),
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

  const getNotificationDeliveries = useCallback(
    (params: { status?: ApmNotificationDelivery['status']; event_id?: string } = {}) =>
      get<ApmNotificationDelivery[]>('/apm/notification-deliveries/', { params }),
    [get]
  );

  const getNotificationRecipients = useCallback(
    (params: { search?: string; limit?: number } = {}) =>
      get<ApmNotificationRecipient[]>('/apm/notification-recipients/', { params }),
    [get]
  );

  const retryNotificationDelivery = useCallback(
    (deliveryId: string, recipients?: string[]) =>
      post<ApmNotificationDelivery>(`/apm/notification-deliveries/${deliveryId}/retry/`,
        recipients === undefined ? {} : { recipients }),
    [post]
  );

  return {
    getServices,
    getService,
    getInstances,
    getInstancePage,
    setInstanceOrganizations,
    setInstanceArchived,
    setServiceOrganizations,
    setServiceArchived,
    getApplications,
    getCloudRegions,
    createApplication,
    updateApplication,
    getIngestSnippet,
    getHealth,
    getServiceRed,
    getSlos,
    createSlo,
    updateSlo,
    deleteSlo,
    setSloEnabled,
    getTraces,
    getTrace,
    getTopology,
    getPolicies,
    createPolicy,
    updatePolicy,
    deletePolicy,
    setPolicyEnabled,
    testPolicy,
    getEvents,
    getNotificationChannels,
    getNotificationDeliveries,
    getNotificationRecipients,
    retryNotificationDelivery,
    isLoading,
  };
};

export default useApmApi;
