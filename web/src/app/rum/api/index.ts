'use client';

import { useCallback } from 'react';

import { useRumApi, useRumAuthReady } from '@/app/rum/api/client';
import {
  withDegradation,
  type PipelineDegradation,
  type RumAnalyticsRange,
} from '@/app/rum/lib/degradation';
import { metricOrZero } from '@/app/rum/lib/metrics';

export interface RumApplicationView {
  application: string;
  resourceId?: string;
  tenantId?: string;
  enabled: boolean;
  revision?: number;
  browserKeys?: string[];
  browserKeyDigests?: string[];
  origins?: string[];
  budgets?: Record<string, number>;
  lastAcceptedAt?: number;
  lastStoredAt?: number;
  projectionPending?: boolean;
  controlUnavailable?: boolean;
}

export interface RumApplicationStatus {
  application: string;
  enabled: boolean;
  status: 'connected' | 'waiting' | 'disabled';
  gateway: { state: 'ok' | 'waiting'; at?: number };
  store: { state: 'ok' | 'waiting'; at?: number };
  controllerUnreachable?: boolean;
  checkedAt: number;
}

export interface RumSnippetInput {
  application: string;
  environment: string;
  release: string;
  browserKey: string;
  collectUrl: string;
  replayUrl: string;
  sdkCdnUrl?: string;
  replay: { enabled: boolean; samplingRate?: number };
}

export interface RumSnippetSet {
  npm: string;
  react: string;
  generic: string;
  cdn: string;
}

export type RumMeta = {
  publicOrigin?: string;
  collectUrl: string;
  replayUrl: string;
  sdkCdnUrl: string;
  controlConfigured?: boolean;
  analyticsConfigured?: boolean;
  controlAvailable?: boolean;
  analyticsAvailable?: boolean;
} & PipelineDegradation;

export type RumHealth = {
  controlConfigured?: boolean;
  analyticsConfigured?: boolean;
  controlAvailable?: boolean;
  analyticsAvailable?: boolean;
} & PipelineDegradation;

export type RumApplicationHealthItem = RumApplicationView & {
  environment?: string;
  release?: string;
  sdkVersion?: string;
  sessions: number;
  views: number | null;
  errors: number | null;
  lcpP75: number | null;
  inpP75: number | null;
  errorRate: number;
  lastSeenMs?: number;
};

export type RumApplicationsCatalog = PipelineDegradation & {
  configured: boolean;
  range: RumAnalyticsRange | string;
  applications: RumApplicationHealthItem[];
  sparklines: Record<string, Array<number | null>>;
  kpi: {
    poorApps: number;
    sessions: number;
    views: number | null;
    errors: number | null;
    worstLcp: number | null;
    worstInp: number | null;
  };
};

export interface RumOverviewDistribution { key: string; sessions: number; views: number }
export interface RumOverviewCountry { country: string; sessions: number; views: number }
export interface RumSessionTrendPoint {
  bucketStartMs?: number;
  atMs?: number;
  sessions?: number;
  total?: number;
  errored?: number;
}

export type RumApplicationOverview = PipelineDegradation & {
  application: string;
  enabled: boolean;
  range: RumAnalyticsRange | string;
  kpi: RumApplicationHealthItem;
  sparkline: Array<number | null>;
  trend: RumSessionTrendPoint[];
  countries: RumOverviewCountry[];
  devices: { mobile: number; desktop: number };
  environments: RumOverviewDistribution[];
  releases: RumOverviewDistribution[];
};

export interface RumSessionRow {
  sessionId: string;
  application: string;
  startTime: string;
  endTime?: string;
  eventCount?: number;
  viewCount: number;
  errorCount: number;
  actionCount?: number;
  vitalCount?: number;
  hasReplay?: boolean;
  entryRoute: string;
  userAgent?: string;
  geoCountry?: string;
  geoCity?: string;
  userId?: string;
  environment?: string;
  release?: string;
}

export type RumSessionListPage = PipelineDegradation & {
  sessions: RumSessionRow[];
  summary?: { total: number; errored: number; replayed: number; medianDurationMs: number };
  replayScanTruncated?: boolean;
};

export type RumSessionJourney = PipelineDegradation & {
  session: RumSessionRow | null;
  views: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
  errors: Array<Record<string, unknown>>;
  vitals: Array<Record<string, unknown>>;
  network: Array<Record<string, unknown>>;
  console: Array<Record<string, unknown>>;
};

export interface RumReplaySegment {
  sequence: number;
  startedAt: string;
  endedAt: string;
  eventCount: number;
  compressedBytes: number;
  uncompressedBytes: number;
  hasFullSnapshot: boolean;
  ref: string;
}

export type RumReplayManifest = PipelineDegradation & {
  state: 'ready' | 'pending' | 'not-recorded' | 'unavailable';
  retentionDays: number;
  recordings: Array<{
    recordingId: string;
    pageId: string;
    segments: RumReplaySegment[];
  }>;
};

export interface RumReplayGrant {
  targetRef: string;
  targetIncluded: boolean;
  segments: Array<{ ref: string; sequence: number; url: string; expiresAtMs: number }>;
  controlUnavailable?: boolean;
}

export interface RumViewDist { good: number; needsImprove: number; poor: number; missing: number }
export interface RumViewDeviceMix { mobile: number; desktop: number }
export interface RumViewMom { viewsDeltaPct?: number; hasDelta: boolean; spark: number[] }

export interface RumViewAggregateRow {
  key: string;
  release?: string;
  route?: string;
  views: number | null;
  errors?: number | null;
  sessions: number | null;
  lcpP75: number | null;
  lcpTarget?: string;
  lcpAttribution?: string;
  inpP75: number | null;
  inpTarget?: string;
  inpAttribution?: string;
  clsP75: number | null;
  loadingP75: number | null;
  dist: RumViewDist;
  impact: number;
  mom: RumViewMom;
  deviceMix: RumViewDeviceMix;
}

export type RumViewListPage = PipelineDegradation & {
  mode: string;
  summary: { lcpP75: number | null; inpP75: number | null; clsP75: number | null };
  releases: string[];
  rows: RumViewAggregateRow[];
};

export interface RumErrorIssueItem {
  application: string;
  errorType: string;
  normalizedMessage: string;
  fingerprint: string;
  sampleMessage: string;
  sampleFrames: string;
  count: number;
  affectedSessions: number;
  affectedUsers: number;
  firstSeen: string;
  lastSeen: string;
  lastRelease: string;
  status: string;
  sparkline: number[];
  signals: string[];
}

export type RumErrorIssuePage = PipelineDegradation & {
  issues: RumErrorIssueItem[];
};

export interface RumErrorOccurrence {
  eventId: string;
  sessionId: string;
  userId: string;
  source: string;
  timestamp: string;
  hasReplay: boolean;
  traceId: string;
}

export type RumErrorDetail = RumErrorIssueItem &
  PipelineDegradation & {
    note?: string;
    resolvedAt?: string;
    resolvedVersion?: string;
    ignoredUntil?: string;
    occurrences: RumErrorOccurrence[];
  };

export interface RumSourceMapFrame {
  file: string;
  functionName?: string;
  line?: number;
  column?: number;
  resolved: boolean;
}

export interface RumSourceMapRestoreResult {
  frames: RumSourceMapFrame[];
  anyResolved: boolean;
  outcome: 'resolved' | 'missing_release' | 'missing_artifact' | 'invalid_map' | 'unmapped_position';
  sourcemapId?: string;
}

export interface RumFunnelItem {
  id: string;
  name: string;
  steps: string[];
  application?: string;
  createdAt?: string;
  updatedAt?: string;
}

export type RumFunnelReachResult = PipelineDegradation & {
  steps: string[];
  reached: number[];
  truncated?: boolean;
};

export interface RumReleaseRow {
  release: string;
  errorCount: number;
  distinctIssues: number;
  affectedSessions: number;
  affectedUsers: number;
  firstSeen: string;
  lastSeen: string;
  lcpP75: number;
  inpP75: number;
  isBaseline?: boolean;
  errorDelta?: number;
  sessionsDelta?: number;
  usersDelta?: number;
  issuesDelta?: number;
  newIssues: number;
  lcpP75Delta?: number;
  inpP75Delta?: number;
  suspectedRegression: boolean;
}

export type RumReleasePage = PipelineDegradation & {
  releases: RumReleaseRow[];
};

export interface RumSourceMapItem {
  id: string;
  application: string;
  release: string;
  fileName: string;
  createdBy: string;
  createdAt: string;
}

export interface RumNotificationTarget {
  channelId: number;
  channelName?: string;
  channelType?: string;
  deliveryMode: 'message' | 'alert_event_copy' | string;
  recipientMode: 'none' | 'system_user' | 'free_text' | string;
  recipients: string[];
}

export interface RumNotificationChannel {
  id: number;
  name: string;
  channel_type: string;
  description?: string;
  delivery_mode: 'message' | 'alert_event_copy' | string;
  recipient_mode: 'none' | 'system_user' | 'free_text' | string;
  availability?: 'available' | 'unavailable' | string;
}

export interface RumNotificationRecipient {
  id: number;
  username: string;
  display_name?: string;
}

export interface RumMonitorItem {
  id: string;
  name: string;
  application: string;
  organizations?: number[];
  organizationsDisplay?: string[];
  metric: string;
  severity: string;
  comparator?: string;
  warnThreshold: number;
  criticalThreshold: number;
  evaluationWindowMinutes?: number;
  forDurationSec: number;
  noDataAfter?: number;
  renotifyMinutes?: number | null;
  handlers?: Array<string | number>;
  handlersDisplay?: string[];
  notificationTargets?: RumNotificationTarget[];
  enabled: boolean;
  firing: boolean;
  lastSucceededAt?: string | null;
  lastFailedAt?: string | null;
  lastEvaluationResult?: string;
  createdAt: string;
  updatedAt: string;
}

export interface RumAlertItem {
  id: string;
  policyId: string;
  policyName?: string;
  application?: string;
  metric?: string;
  severity?: string;
  status: string;
  currentValue?: number | null;
  organizations?: number[];
  handlers?: Array<string | number>;
  handlersDisplay?: string[];
  notification?: { pending: number; delivered: number; failed: number };
  startedAt?: string;
  endedAt?: string | null;
  lastEventAt?: string;
  createdAt: string;
}

export interface RumAlertTimelineEvent {
  id: string;
  action: string;
  occurredAt?: string;
  severity?: string;
  value?: number | null;
  content?: Record<string, unknown>;
}

export interface RumAlertDeliveryItem {
  id: string;
  channelName?: string;
  deliveryMode?: string;
  status: string;
  attempts?: number;
  lastErrorCode?: string;
  lastErrorMessage?: string;
}

export interface RumAlertQuery {
  page?: number;
  limit?: number;
  status?: 'active' | 'history' | '';
  application?: string;
  keyword?: string;
  handler?: string;
  myAlert?: boolean;
}

export interface RumAlertEventPage {
  items: RumAlertItem[];
  total: number;
  page: number;
  limit: number;
}

export interface RumAlertTrendPoint {
  atMs: number;
  value: number | null;
}

/** Keep a real number, including 0. Null, missing, and non-numeric samples stay empty. */
export function parseAlertTrendValue(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  return value;
}

export function parseAlertTrend(raw: unknown): RumAlertTrendPoint[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => {
    if (item === null || typeof item !== 'object') return { atMs: 0, value: null };
    const point = item as { atMs?: unknown; value?: unknown };
    const atMs = typeof point.atMs === 'number' && Number.isFinite(point.atMs) ? point.atMs : 0;
    return { atMs, value: parseAlertTrendValue(point.value) };
  });
}

export interface RumAlertEventDetail {
  alert: RumAlertItem;
  events: RumAlertTimelineEvent[];
  deliveries: RumAlertDeliveryItem[];
  trend: RumAlertTrendPoint[];
}

export interface RumEraseJob {
  id: string;
  application: string;
  endUserId: string;
  scope: string;
  status: string;
  requestedBy?: string;
  result?: Record<string, unknown>;
  createdAt: string;
  updatedAt?: string;
}

export type RumEraseResult = Record<string, unknown> & {
  ledger?: RumEraseJob;
};

export interface RumSavedView {
  id: string;
  screen: string;
  name: string;
  contextJson: string;
  shared: boolean;
  owner: string;
  createdAt: string;
  updatedAt: string;
}

export function normalizeApplication(app: RumApplicationView): RumApplicationView {
  return {
    ...app,
    origins: Array.isArray(app.origins) ? app.origins : [],
    browserKeys: Array.isArray(app.browserKeys) ? app.browserKeys : [],
    browserKeyDigests: Array.isArray(app.browserKeyDigests) ? app.browserKeyDigests : [],
  };
}

function emptyHealth(name: string, enabled = false): RumApplicationHealthItem {
  return {
    application: name,
    enabled,
    sessions: 0,
    views: 0,
    errors: 0,
    lcpP75: 0,
    inpP75: 0,
    errorRate: 0,
  };
}

/** Shared RUM BFF calls used by host pages (`/api/ops/rum` → BK-Lite `/rum`). */
export function useRumQueries() {
  const api = useRumApi();
  const authReady = useRumAuthReady();

  const getMeta = useCallback(async () => {
    const data = await api.get<RumMeta>('/meta/');
    return withDegradation(data || ({} as RumMeta));
  }, [api]);

  const getHealth = useCallback(async () => {
    const data = await api.get<RumHealth>('/health/');
    return withDegradation(data || ({} as RumHealth));
  }, [api]);

  const listApplications = useCallback(async (brief = false) => {
    const data = await api.get<RumApplicationView[]>(
      '/applications/',
      brief ? { params: { brief: '1' } } : undefined,
    );
    return (Array.isArray(data) ? data : []).map(normalizeApplication);
  }, [api]);

  const getApplication = useCallback(
    async (name: string) => {
      const data = await api.get<RumApplicationView>(`/applications/${encodeURIComponent(name)}/`);
      return normalizeApplication(data);
    },
    [api],
  );

  const createApplication = useCallback(
    async (body: { application: string; origins: string[]; budgets?: Record<string, number> }) => {
      const data = await api.post<RumApplicationView>('/applications/', body);
      return normalizeApplication(data);
    },
    [api],
  );

  const updateApplication = useCallback(
    async (name: string, body: { origins?: string[]; enabled?: boolean; budgets?: Record<string, number> }) => {
      const data = await api.put<RumApplicationView>(`/applications/${encodeURIComponent(name)}/`, body);
      return normalizeApplication(data);
    },
    [api],
  );

  const disableApplication = useCallback(
    async (name: string) => {
      const data = await api.post<RumApplicationView>(
        `/applications/${encodeURIComponent(name)}/disable/`,
      );
      return normalizeApplication(data);
    },
    [api],
  );

  const reissueKey = useCallback(
    async (name: string) => {
      const data = await api.post<RumApplicationView>(
        `/applications/${encodeURIComponent(name)}/keys/`,
      );
      return normalizeApplication(data);
    },
    [api],
  );

  const getApplicationStatus = useCallback(
    async (name: string) =>
      api.get<RumApplicationStatus>(`/applications/${encodeURIComponent(name)}/status/`),
    [api],
  );

  const buildSnippets = useCallback(
    async (input: RumSnippetInput) => api.post<RumSnippetSet>('/snippets/', input),
    [api],
  );

  const getAnalyticsCatalog = useCallback(
    async (range: RumAnalyticsRange = '24h') => {
      const data = await api.get<RumApplicationsCatalog>('/analytics/applications/', {
        params: { range },
      });
      return withDegradation({
        configured: Boolean(data?.configured),
        range: data?.range || range,
        applications: Array.isArray(data?.applications)
          ? data.applications.map((item) => ({
            ...normalizeApplication(item),
            sessions: Number(item.sessions) || 0,
            views: metricOrZero(item.views),
            errors: metricOrZero(item.errors),
            lcpP75: metricOrZero(item.lcpP75),
            inpP75: metricOrZero(item.inpP75),
            errorRate: Number(item.errorRate) || 0,
            environment: item.environment,
            release: item.release,
            sdkVersion: item.sdkVersion,
            lastSeenMs: item.lastSeenMs,
          }))
          : [],
        sparklines: data?.sparklines && typeof data.sparklines === 'object' ? data.sparklines : {},
        kpi: data?.kpi || {
          poorApps: 0,
          sessions: 0,
          views: 0,
          errors: 0,
          worstLcp: 0,
          worstInp: 0,
        },
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const getApplicationOverview = useCallback(
    async (name: string, range: RumAnalyticsRange = '24h') => {
      const data = await api.get<RumApplicationOverview>(
        `/applications/${encodeURIComponent(name)}/overview/`,
        { params: { range } },
      );
      return withDegradation({
        application: data?.application || name,
        enabled: Boolean(data?.enabled),
        range: data?.range || range,
        kpi: data?.kpi
          ? {
            ...emptyHealth(name, Boolean(data.enabled)),
            ...data.kpi,
            sessions: Number(data.kpi.sessions) || 0,
            views: metricOrZero(data.kpi.views),
            errors: metricOrZero(data.kpi.errors),
            lcpP75: metricOrZero(data.kpi.lcpP75),
            inpP75: metricOrZero(data.kpi.inpP75),
            errorRate: Number(data.kpi.errorRate) || 0,
          }
          : emptyHealth(name, Boolean(data?.enabled)),
        sparkline: Array.isArray(data?.sparkline) ? data.sparkline : [],
        trend: Array.isArray(data?.trend) ? data.trend : [],
        countries: Array.isArray(data?.countries) ? data.countries : [],
        devices: data?.devices || { mobile: 0, desktop: 0 },
        environments: Array.isArray(data?.environments) ? data.environments : [],
        releases: Array.isArray(data?.releases) ? data.releases : [],
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const listSessions = useCallback(
    async (params: Record<string, string>) => {
      const data = await api.get<RumSessionListPage>('/sessions/', {
        params,
      });
      return withDegradation({
        sessions: Array.isArray(data?.sessions) ? data.sessions : [],
        summary: data?.replayScanTruncated
          ? undefined
          : data?.summary || { total: 0, errored: 0, replayed: 0, medianDurationMs: 0 },
        replayScanTruncated: Boolean(data?.replayScanTruncated),
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const listSessionsTrend = useCallback(
    async (params: Record<string, string>) => {
      const data = await api.get<{ points?: RumSessionTrendPoint[] }>('/sessions/trend/', {
        params,
      });
      return Array.isArray(data?.points) ? data.points : [];
    },
    [api],
  );

  const getSession = useCallback(
    async (sessionId: string, application: string, range = '24h') => {
      const data = await api.get<RumSessionJourney>(
        `/sessions/${encodeURIComponent(sessionId)}/`,
        {
          params: { application, range },
        },
      );
      return withDegradation({
        session: data?.session || null,
        views: Array.isArray(data?.views) ? data.views : [],
        actions: Array.isArray(data?.actions) ? data.actions : [],
        errors: Array.isArray(data?.errors) ? data.errors : [],
        vitals: Array.isArray(data?.vitals) ? data.vitals : [],
        network: Array.isArray(data?.network) ? data.network : [],
        console: Array.isArray(data?.console) ? data.console : [],
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const getReplayManifest = useCallback(
    async (application: string, session: string) => {
      const data = await api.get<RumReplayManifest>('/replay/manifest/', {
        params: { application, session },
      });
      return withDegradation({
        state: data?.state || 'unavailable',
        retentionDays: Number(data?.retentionDays) || 0,
        recordings: Array.isArray(data?.recordings) ? data.recordings : [],
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const createReplayGrant = useCallback(
    async (application: string, session: string, targetRef: string) =>
      api.post<RumReplayGrant>('/replay/grants/', { application, session, targetRef }),
    [api],
  );

  const listViews = useCallback(
    async (params: Record<string, string>) => {
      const data = await api.get<RumViewListPage>('/views/', {
        params,
      });
      return withDegradation({
        mode: data?.mode || 'route',
        summary: {
          lcpP75: metricOrZero(data?.summary?.lcpP75),
          inpP75: metricOrZero(data?.summary?.inpP75),
          clsP75: metricOrZero(data?.summary?.clsP75),
        },
        releases: Array.isArray(data?.releases) ? data.releases : [],
        rows: Array.isArray(data?.rows)
          ? data.rows.map((row) => ({
            ...row,
            views: metricOrZero(row.views),
            errors: Object.prototype.hasOwnProperty.call(row, 'errors') ? metricOrZero(row.errors) : undefined,
            sessions: metricOrZero(row.sessions),
            lcpP75: metricOrZero(row.lcpP75),
            inpP75: metricOrZero(row.inpP75),
            clsP75: metricOrZero(row.clsP75),
            loadingP75: metricOrZero(row.loadingP75),
            impact: Number(row.impact) || 0,
            dist: row.dist || { good: 0, needsImprove: 0, poor: 0, missing: 0 },
            mom: row.mom || { hasDelta: false, spark: [] },
            deviceMix: row.deviceMix || { mobile: 0, desktop: 0 },
          }))
          : [],
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const listErrors = useCallback(
    async (params: Record<string, string>) => {
      const data = await api.get<RumErrorIssuePage>('/errors/', {
        params,
      });
      return withDegradation({
        issues: Array.isArray(data?.issues) ? data.issues : [],
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const getErrorDetail = useCallback(
    async (fingerprint: string, params: Record<string, string>) => {
      const data = await api.get<RumErrorDetail>(`/errors/${encodeURIComponent(fingerprint)}/`, {
        params,
      });
      return withDegradation({
        ...data,
        fingerprint: data?.fingerprint || fingerprint,
        application: data?.application || params.application || '',
        errorType: data?.errorType || '',
        normalizedMessage: data?.normalizedMessage || '',
        sampleMessage: data?.sampleMessage || '',
        sampleFrames: data?.sampleFrames || '[]',
        count: Number(data?.count) || 0,
        affectedSessions: Number(data?.affectedSessions) || 0,
        affectedUsers: Number(data?.affectedUsers) || 0,
        firstSeen: data?.firstSeen || '',
        lastSeen: data?.lastSeen || '',
        lastRelease: data?.lastRelease || '',
        status: data?.status || 'open',
        sparkline: Array.isArray(data?.sparkline) ? data.sparkline : [],
        signals: Array.isArray(data?.signals) ? data.signals : [],
        occurrences: Array.isArray(data?.occurrences) ? data.occurrences : [],
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const updateErrorIssue = useCallback(
    async (fingerprint: string, body: { status?: string; note?: string; resolvedVersion?: string }) =>
      api.patch(`/errors/issues/${encodeURIComponent(fingerprint)}/`, body),
    [api],
  );

  const restoreSourceMap = useCallback(
    async (application: string, release: string, frames: unknown[]) =>
      api.post<RumSourceMapRestoreResult>('/sourcemaps/restore/', {
        application,
        release,
        frames,
      }),
    [api],
  );

  const listFunnels = useCallback(async () => {
    const data = await api.get<RumFunnelItem[]>('/funnels/');
    return Array.isArray(data) ? data : [];
  }, [api]);

  const createFunnel = useCallback(
    async (body: { name: string; steps: string[]; application?: string }) =>
      api.post<RumFunnelItem>('/funnels/', body),
    [api],
  );

  const updateFunnel = useCallback(
    async (id: string, body: { name: string; steps: string[]; application?: string }) =>
      api.put<RumFunnelItem>(`/funnels/${encodeURIComponent(id)}/`, body),
    [api],
  );

  const deleteFunnel = useCallback(
    async (id: string) => {
      await api.del(`/funnels/${encodeURIComponent(id)}/`);
    },
    [api],
  );

  const funnelReach = useCallback(
    async (id: string, params: Record<string, string>) => {
      const data = await api.get<RumFunnelReachResult>(`/funnels/${encodeURIComponent(id)}/reach/`, {
        params,
      });
      return withDegradation({
        steps: Array.isArray(data?.steps) ? data.steps : [],
        reached: Array.isArray(data?.reached) ? data.reached.map(Number) : [],
        truncated: Boolean(data?.truncated),
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const listReleases = useCallback(
    async (params: Record<string, string>) => {
      const data = await api.get<RumReleasePage>('/releases/', {
        params,
      });
      return withDegradation({
        releases: Array.isArray(data?.releases)
          ? data.releases.map((row) => ({
            ...row,
            release: row.release || '',
            errorCount: Number(row.errorCount) || 0,
            distinctIssues: Number(row.distinctIssues) || 0,
            affectedSessions: Number(row.affectedSessions) || 0,
            affectedUsers: Number(row.affectedUsers) || 0,
            firstSeen: row.firstSeen || '',
            lastSeen: row.lastSeen || '',
            lcpP75: Number(row.lcpP75) || 0,
            inpP75: Number(row.inpP75) || 0,
            newIssues: Number(row.newIssues) || 0,
            suspectedRegression: Boolean(row.suspectedRegression),
            errorDelta: row.errorDelta == null ? undefined : Number(row.errorDelta) || 0,
            sessionsDelta: row.sessionsDelta == null ? undefined : Number(row.sessionsDelta) || 0,
            usersDelta: row.usersDelta == null ? undefined : Number(row.usersDelta) || 0,
            issuesDelta: row.issuesDelta == null ? undefined : Number(row.issuesDelta) || 0,
            lcpP75Delta: row.lcpP75Delta == null ? undefined : Number(row.lcpP75Delta) || 0,
            inpP75Delta: row.inpP75Delta == null ? undefined : Number(row.inpP75Delta) || 0,
          }))
          : [],
        controlUnavailable: data?.controlUnavailable,
        analyticsUnavailable: data?.analyticsUnavailable,
      });
    },
    [api],
  );

  const putBaseline = useCallback(
    async (application: string, baselineRelease: string) =>
      api.put(`/releases/baselines/${encodeURIComponent(application)}/`, { baselineRelease }),
    [api],
  );

  const listSourceMaps = useCallback(
    async (application = '') => {
      const data = await api.get<RumSourceMapItem[]>('/sourcemaps/', {
        params: application ? { application } : undefined,
      });
      return Array.isArray(data) ? data : [];
    },
    [api],
  );

  const uploadSourceMap = useCallback(
    async (input: { application: string; release: string; asset: string; file: File }) => {
      const body = new FormData();
      body.set('application', input.application);
      body.set('release', input.release);
      body.set('asset', input.asset);
      body.set('file', input.file);
      return api.post<RumSourceMapItem>('/sourcemaps/', body, {
        headers: { 'Content-Type': undefined },
      });
    },
    [api],
  );

  const rotateSourceMapCredential = useCallback(
    async (application: string) =>
      api.post<{ token: string }>(
        `/sourcemaps/credentials/${encodeURIComponent(application)}/rotate/`,
      ),
    [api],
  );

  const listMonitors = useCallback(async () => {
    const data = await api.get<RumMonitorItem[]>('/monitors/');
    return Array.isArray(data) ? data : [];
  }, [api]);

  const createMonitor = useCallback(
    async (body: Record<string, unknown>) => api.post<RumMonitorItem>('/monitors/', body),
    [api],
  );

  const updateMonitor = useCallback(
    async (id: string, body: Record<string, unknown>) =>
      api.put<RumMonitorItem>(`/monitors/${encodeURIComponent(id)}/`, body),
    [api],
  );

  const deleteMonitor = useCallback(
    async (id: string) => api.del(`/monitors/${encodeURIComponent(id)}/`),
    [api],
  );

  const listAlertEvents = useCallback(async (pageOrQuery: number | RumAlertQuery = 1, limit = 20) => {
    const query: RumAlertQuery = typeof pageOrQuery === 'number' ? { page: pageOrQuery, limit } : pageOrQuery;
    const page = query.page || 1;
    const pageLimit = query.limit || limit;
    const params: Record<string, string> = {
      page: String(page),
      limit: String(pageLimit),
    };
    if (query.status) params.status = query.status;
    if (query.application) params.application = query.application;
    if (query.keyword) params.keyword = query.keyword;
    if (query.handler) params.handler = query.handler;
    if (query.myAlert) params.my_alert = '1';
    const data = await api.get<RumAlertEventPage>('/alert-events/', { params });
    return {
      items: Array.isArray(data?.items) ? data.items : [],
      total: Number(data?.total) || 0,
      page: Number(data?.page) || page,
      limit: Number(data?.limit) || pageLimit,
    };
  }, [api]);

  const getAlertEvent = useCallback(
    async (id: string) => {
      const data = await api.get<RumAlertEventDetail>(`/alert-events/${encodeURIComponent(id)}/`);
      return {
        alert: data?.alert ?? ({} as RumAlertItem),
        events: Array.isArray(data?.events) ? data.events : [],
        deliveries: Array.isArray(data?.deliveries) ? data.deliveries : [],
        trend: parseAlertTrend(data?.trend),
      };
    },
    [api],
  );

  const claimAlert = useCallback(
    async (id: string) => api.post<RumAlertItem>(`/alert-events/${encodeURIComponent(id)}/claim/`, {}),
    [api],
  );

  const assignAlert = useCallback(
    async (id: string, handlers: Array<string | number>) =>
      api.post<RumAlertItem>(`/alert-events/${encodeURIComponent(id)}/assign/`, { handlers }),
    [api],
  );

  const reassignAlert = useCallback(
    async (id: string, handlers: Array<string | number>) =>
      api.post<RumAlertItem>(`/alert-events/${encodeURIComponent(id)}/reassign/`, { handlers }),
    [api],
  );

  const closeAlert = useCallback(
    async (id: string) => api.post<RumAlertItem>(`/alert-events/${encodeURIComponent(id)}/close/`, {}),
    [api],
  );

  const retryAlertDelivery = useCallback(
    async (alertId: string, deliveryId: string) =>
      api.post(`/alert-events/${encodeURIComponent(alertId)}/deliveries/${encodeURIComponent(deliveryId)}/retry/`, {}),
    [api],
  );

  const listNotificationChannels = useCallback(
    async (organizationIds: number[]) => {
      const data = await api.get<RumNotificationChannel[]>('/notification-channels/', {
        params: { organization_ids: organizationIds.join(',') },
      });
      return Array.isArray(data) ? data : [];
    },
    [api],
  );

  const searchNotificationRecipients = useCallback(
    async (organizationIds: number[], search = '') => {
      const data = await api.get<RumNotificationRecipient[]>('/notification-recipients/', {
        params: { organization_ids: organizationIds.join(','), search },
      });
      return Array.isArray(data) ? data : [];
    },
    [api],
  );

  const listEraseJobs = useCallback(
    async (params: Record<string, string> = {}) => {
      const data = await api.get<RumEraseJob[]>('/compliance/erase/', { params });
      return Array.isArray(data) ? data : [];
    },
    [api],
  );

  const eraseCompliance = useCallback(
    async (body: { application: string; endUserId: string }) =>
      api.post<RumEraseResult>('/compliance/erase/', body),
    [api],
  );

  const listSavedViews = useCallback(
    async (screen: string) => {
      const data = await api.get<RumSavedView[]>('/saved-views/', {
        params: { screen },
      });
      return Array.isArray(data) ? data : [];
    },
    [api],
  );

  const createSavedView = useCallback(
    async (body: { screen: string; name: string; contextJson: string; shared: boolean }) =>
      api.post<RumSavedView>('/saved-views/', body),
    [api],
  );

  const deleteSavedView = useCallback(
    async (id: string) => api.del(`/saved-views/${encodeURIComponent(id)}/`),
    [api],
  );

  return {
    ...api,
    authReady,
    getMeta,
    getHealth,
    listApplications,
    getApplication,
    createApplication,
    updateApplication,
    disableApplication,
    reissueKey,
    getApplicationStatus,
    buildSnippets,
    getAnalyticsCatalog,
    getApplicationOverview,
    listSessions,
    listSessionsTrend,
    getSession,
    getReplayManifest,
    createReplayGrant,
    listViews,
    listErrors,
    getErrorDetail,
    updateErrorIssue,
    restoreSourceMap,
    listFunnels,
    createFunnel,
    updateFunnel,
    deleteFunnel,
    funnelReach,
    listReleases,
    putBaseline,
    listSourceMaps,
    uploadSourceMap,
    rotateSourceMapCredential,
    listMonitors,
    createMonitor,
    updateMonitor,
    deleteMonitor,
    listAlertEvents,
    getAlertEvent,
    claimAlert,
    assignAlert,
    reassignAlert,
    closeAlert,
    retryAlertDelivery,
    listNotificationChannels,
    searchNotificationRecipients,
    listEraseJobs,
    eraseCompliance,
    listSavedViews,
    createSavedView,
    deleteSavedView,
  };
}
