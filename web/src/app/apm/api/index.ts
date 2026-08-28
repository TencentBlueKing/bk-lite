import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { RequestConfig } from '@/utils/request';
import type {
  ApmApplication,
  ApmApplicationInput,
  ApmCloudRegion,
  ApmDashboard,
  ApmDeploymentEvent,
  ApmDeploymentStatus,
  ApmIngestSnippet,
  ApmIngestSnippetInput,
  ApmTimeWindow,
  ApmEvent,
  ApmEventQuery,
  ApmAlert,
  ApmAlertMetricSnapshot,
  ApmAlertQuery,
  ApmEventSnapshot,
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
  ApmSpanPage,
  ApmSpanSearchParams,
  ApmTopologyGraph,
  ApmIssuePage,
  ApmIssueSearchParams,
  InstanceStatus,
} from '@/app/apm/types';

interface InstanceQuery {
  application?: string;
  environment?: string;
  status?: InstanceStatus;
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

  const getApplication = useCallback(
    (applicationId: string) => get<ApmApplication>(`/apm/applications/${applicationId}/`),
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

  const getDeployments = useCallback(
    (params: {
      service_id?: string;
      environment?: string;
      status?: ApmDeploymentStatus;
      started_at?: string;
      ended_at?: string;
      page?: number;
      page_size?: number;
    } = {}) => get<ApmPage<ApmDeploymentEvent>>('/apm/deployments/', { params }),
    [get]
  );

  const getDashboard = useCallback(
    (window: ApmTimeWindow) => get<ApmDashboard>('/apm/dashboard/', { params: { window } }),
    [get]
  );

  const getServiceRed = useCallback(
    (serviceId: string, environment: string, startedAt?: string, endedAt?: string, endpoint?: string) =>
      get<ApmServiceRed>(`/apm/services/${serviceId}/metrics/`, {
        params: { environment, started_at: startedAt, ended_at: endedAt, endpoint },
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

  const getSpans = useCallback(
    (params: ApmSpanSearchParams) => get<ApmSpanPage>('/apm/spans/', { params }),
    [get]
  );

  const getIssues = useCallback(
    (params: ApmIssueSearchParams = {}) => get<ApmIssuePage>('/apm/issues/', { params }),
    [get]
  );

  const getTrace = useCallback(
    (traceId: string) => get<ApmTraceDetail>(`/apm/traces/${traceId}/`),
    [get]
  );

  const getTopology = useCallback(
    (params: {
      started_at: string;
      ended_at: string;
      environment?: string;
      status?: 'ok' | 'error';
      span_name?: string;
      min_duration_ms?: number;
      include_inferred?: boolean;
      include_user_request?: boolean;
    }) => get<ApmTopologyGraph>('/apm/topology/', { params }),
    [get]
  );

  const getPolicies = useCallback(() => get<ApmPolicy[]>('/apm/policies/'), [get]);

  const getPolicy = useCallback(
    (policyId: string) => get<ApmPolicy>(`/apm/policies/${policyId}/`),
    [get]
  );

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

  const previewPolicy = useCallback(
    (payload: ApmPolicyInput, suppressErrorNotification = false) => post<ApmPolicyQueryResult>(
      '/apm/policies/preview/',
      payload,
      suppressErrorNotification ? { suppressErrorNotification: true } : undefined,
    ),
    [post]
  );

  const getEvents = useCallback(
    (params: ApmEventQuery = {}) => get<ApmEvent[]>('/apm/events/', { params }),
    [get]
  );

  const getAlerts = useCallback(
    (params: ApmAlertQuery = {}) => get<ApmAlert[]>('/apm/alerts/', { params }),
    [get]
  );

  const getAlertDistribution = useCallback(
    (params: Pick<ApmAlertQuery, 'started_at' | 'ended_at' | 'status_group'>) =>
      get<Array<{ time: string; critical: number; error: number; warning: number }>>(
        '/apm/alerts/distribution/',
        { params }
      ),
    [get]
  );

  const getEventEvidence = useCallback(
    (alertId: string, eventId?: string) =>
      get<ApmEventSnapshot[]>(`/apm/alerts/${alertId}/event-evidence/`, {
        params: eventId ? { event_id: eventId } : {},
      }),
    [get]
  );

  const getAlertSnapshots = useCallback(
    (alertId: string) => get<ApmAlertMetricSnapshot>(`/apm/alerts/${alertId}/snapshots/`),
    [get]
  );

  const closeAlert = useCallback(
    (alertId: string) => post<ApmAlert>(`/apm/alerts/${alertId}/close/`),
    [post]
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
    setServiceOrganizations,
    setServiceArchived,
    getApplications,
    getApplication,
    getCloudRegions,
    createApplication,
    updateApplication,
    getIngestSnippet,
    getHealth,
    getDeployments,
    getDashboard,
    getServiceRed,
    getSlos,
    createSlo,
    updateSlo,
    deleteSlo,
    setSloEnabled,
    getTraces,
    getSpans,
    getIssues,
    getTrace,
    getTopology,
    getPolicies,
    getPolicy,
    createPolicy,
    updatePolicy,
    deletePolicy,
    setPolicyEnabled,
    testPolicy,
    previewPolicy,
    getEvents,
    getAlerts,
    getAlertDistribution,
    getAlertSnapshots,
    getEventEvidence,
    closeAlert,
    getNotificationChannels,
    getNotificationDeliveries,
    getNotificationRecipients,
    retryNotificationDelivery,
    isLoading,
  };
};

export default useApmApi;
