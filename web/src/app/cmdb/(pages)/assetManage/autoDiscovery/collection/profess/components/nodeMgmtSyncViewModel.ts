import type { NodeMgmtSyncStatus } from '@/app/cmdb/types/autoDiscovery';

export type NodeMgmtSyncBadgeStatus = 'success' | 'processing' | 'default' | 'error' | 'warning';

export const NODE_MGMT_SYNC_STATUS_BADGE: Record<NodeMgmtSyncStatus, NodeMgmtSyncBadgeStatus> = {
  waiting_sync: 'warning',
  running: 'processing',
  submitted: 'processing',
  success: 'success',
  partial_success: 'warning',
  blocked: 'error',
  failed: 'error',
  timeout: 'error',
};

const STATUS_TEXT_KEYS: Record<NodeMgmtSyncStatus, string> = {
  waiting_sync: 'Collection.nodeMgmtSync.status.waitingSync',
  running: 'Collection.nodeMgmtSync.status.running',
  submitted: 'Collection.nodeMgmtSync.status.submitted',
  success: 'Collection.nodeMgmtSync.status.success',
  partial_success: 'Collection.nodeMgmtSync.status.partialSuccess',
  blocked: 'Collection.nodeMgmtSync.status.blocked',
  failed: 'Collection.nodeMgmtSync.status.failed',
  timeout: 'Collection.nodeMgmtSync.status.timeout',
};

const LEGACY_STATUS_MAP: Record<string, NodeMgmtSyncStatus> = {
  error: 'failed',
  writing: 'running',
  force_stop: 'blocked',
};

const KNOWN_STATUSES = new Set<NodeMgmtSyncStatus>(Object.keys(STATUS_TEXT_KEYS) as NodeMgmtSyncStatus[]);

export const normalizeNodeMgmtSyncStatus = (rawStatus: unknown): {
  status: NodeMgmtSyncStatus | null;
  isUnknown: boolean;
} => {
  if (rawStatus === null || rawStatus === undefined || rawStatus === '') {
    return { status: null, isUnknown: false };
  }
  if (typeof rawStatus === 'string' && KNOWN_STATUSES.has(rawStatus as NodeMgmtSyncStatus)) {
    return { status: rawStatus as NodeMgmtSyncStatus, isUnknown: false };
  }
  if (typeof rawStatus === 'string' && LEGACY_STATUS_MAP[rawStatus]) {
    return { status: LEGACY_STATUS_MAP[rawStatus], isUnknown: false };
  }
  return { status: 'blocked', isUnknown: true };
};

export const getNodeMgmtSyncStatusTextKey = (status: NodeMgmtSyncStatus, isUnknown = false) =>
  isUnknown ? 'Collection.nodeMgmtSync.status.unknown' : STATUS_TEXT_KEYS[status];

const REASON_TEXT_KEYS: Record<string, string> = {
  SYNC_REQUIRED: 'Collection.nodeMgmtSync.reason.syncRequired',
  RUN_ALREADY_ACTIVE: 'Collection.nodeMgmtSync.reason.runAlreadyActive',
  RUN_TIMEOUT: 'Collection.nodeMgmtSync.reason.runTimeout',
  RUN_FAILED: 'Collection.nodeMgmtSync.reason.runFailed',
  NODE_QUERY_FAILED: 'Collection.nodeMgmtSync.reason.nodeQueryFailed',
  NODE_QUERY_TIMEOUT: 'Collection.nodeMgmtSync.reason.nodeQueryTimeout',
  NODE_PAGE_LIMIT_EXCEEDED: 'Collection.nodeMgmtSync.reason.nodePageLimitExceeded',
  INVALID_REGION_CODE: 'Collection.nodeMgmtSync.reason.invalidRegionCode',
  NO_ACCESS_POINT: 'Collection.nodeMgmtSync.reason.noAccessPoint',
  COLLECT_ALREADY_RUNNING: 'Collection.nodeMgmtSync.reason.collectAlreadyRunning',
  COLLECT_SUBMISSION_BLOCKED: 'Collection.nodeMgmtSync.reason.collectSubmissionBlocked',
  COLLECT_SUBMIT_FAILED: 'Collection.nodeMgmtSync.reason.collectSubmitFailed',
  COLLECT_CHILD_FAILED: 'Collection.nodeMgmtSync.reason.collectChildFailed',
  COLLECT_EXECUTION_ID_MISSING: 'Collection.nodeMgmtSync.reason.collectExecutionMissing',
  COLLECT_EXECUTION_SUPERSEDED: 'Collection.nodeMgmtSync.reason.collectExecutionSuperseded',
  COLLECT_TASK_MISSING: 'Collection.nodeMgmtSync.reason.collectTaskMissing',
  RECONCILE_FAILED: 'Collection.nodeMgmtSync.reason.reconcileFailed',
  NODE_CONFIG_RECONCILE_FAILED: 'Collection.nodeMgmtSync.reason.nodeConfigFailed',
  NODE_CONFIG_DELETE_FAILED: 'Collection.nodeMgmtSync.reason.nodeConfigDeleteFailed',
  NODE_CONFIG_PUSH_FAILED: 'Collection.nodeMgmtSync.reason.nodeConfigPushFailed',
};

const normalizeReasonCode = (reasonCode?: string) => (reasonCode || '').split(':', 1)[0];

export const getNodeMgmtSyncReasonTextKey = (reasonCode?: string) =>
  REASON_TEXT_KEYS[normalizeReasonCode(reasonCode)] || 'Collection.nodeMgmtSync.reason.unknown';

export const getNodeMgmtSyncEmptyStateKey = ({
  status,
  reasonCode,
  total,
  loadFailed = false,
}: {
  status: NodeMgmtSyncStatus | null;
  reasonCode?: string;
  total: number;
  loadFailed?: boolean;
}) => {
  const normalizedReason = normalizeReasonCode(reasonCode);
  if (loadFailed || ['NODE_QUERY_FAILED', 'NODE_QUERY_TIMEOUT', 'NODE_PAGE_LIMIT_EXCEEDED'].includes(normalizedReason)) {
    return 'Collection.nodeMgmtSync.empty.queryFailed';
  }
  if (normalizedReason === 'NO_ACCESS_POINT') {
    return 'Collection.nodeMgmtSync.empty.noAccessPoint';
  }
  if (status === 'waiting_sync') {
    return 'Collection.nodeMgmtSync.status.waitingSync';
  }
  if (status === 'submitted') {
    return 'Collection.nodeMgmtSync.status.submitted';
  }
  if (status === 'partial_success') {
    return 'Collection.nodeMgmtSync.empty.partialFailure';
  }
  if (total === 0 && status === 'success') {
    return 'Collection.nodeMgmtSync.empty.noNodes';
  }
  return 'Collection.nodeMgmtSync.empty.noData';
};

export const getNodeMgmtSyncDisplayEmptyStateKey = (
  payload: {
    message?: { all?: number };
    run?: { status?: unknown; reason_code?: string };
    task?: { health?: { reason_code?: string } };
  },
  loadFailed = false
) => {
  const normalizedStatus = normalizeNodeMgmtSyncStatus(payload.run?.status);
  return getNodeMgmtSyncEmptyStateKey({
    status: normalizedStatus.status,
    reasonCode: payload.run?.reason_code || payload.task?.health?.reason_code,
    total: payload.message?.all || 0,
    loadFailed,
  });
};

export interface NodeMgmtSyncGuardToken {
  generation: number;
  id: number;
}

export const createNodeMgmtSyncRequestGuard = () => {
  let generation = 0;
  let requestId = 0;
  let mutationId = 0;
  let opened = false;

  return {
    open: () => {
      opened = true;
      generation += 1;
      requestId += 1;
      mutationId += 1;
    },
    close: () => {
      opened = false;
      generation += 1;
      requestId += 1;
      mutationId += 1;
    },
    beginRequest: (): NodeMgmtSyncGuardToken => ({ generation, id: ++requestId }),
    isRequestCurrent: (token: NodeMgmtSyncGuardToken) =>
      opened && token.generation === generation && token.id === requestId,
    beginMutation: (): NodeMgmtSyncGuardToken => {
      requestId += 1;
      return { generation, id: ++mutationId };
    },
    isMutationCurrent: (token: NodeMgmtSyncGuardToken) =>
      opened && token.generation === generation && token.id === mutationId,
  };
};
