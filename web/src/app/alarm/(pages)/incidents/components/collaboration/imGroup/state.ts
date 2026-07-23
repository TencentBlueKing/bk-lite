import type {
  IncidentIMGroupStatus,
  IncidentIMPauseReason,
} from '@/app/alarm/types/incidents';

export type IncidentIMGroupViewLabel =
  | 'creating'
  | 'active'
  | 'partial'
  | 'paused'
  | 'incidentClosed'
  | 'createFailed'
  | 'degraded';

export type IncidentIMGroupPrimaryAction = 'details' | 'open' | 'retry' | 'resume';

export interface IncidentIMGroupView {
  label: IncidentIMGroupViewLabel;
  primaryAction: IncidentIMGroupPrimaryAction;
  canPollFast: boolean;
  syncingCount?: number;
}

export interface IncidentIMGroupViewInput {
  status: IncidentIMGroupStatus;
  pause_reason: IncidentIMPauseReason;
  member_summary: {
    total: number;
    joined: number;
    waiting: number;
    failed: number;
  };
}

export const deriveIMGroupView = ({
  status,
  pause_reason: pauseReason,
  member_summary: memberSummary,
}: IncidentIMGroupViewInput): IncidentIMGroupView => {
  const syncingCount = Math.max(
    0,
    memberSummary.total - memberSummary.joined - memberSummary.waiting - memberSummary.failed,
  );
  if (status === 'pending_create' || status === 'creating') {
    return { label: 'creating', primaryAction: 'details', canPollFast: true };
  }
  if (status === 'active_partial') {
    return syncingCount > 0
      ? { label: 'partial', primaryAction: 'retry', canPollFast: true, syncingCount }
      : { label: 'partial', primaryAction: 'retry', canPollFast: false };
  }
  if (status === 'paused') {
    return pauseReason === 'incident_closed'
      ? { label: 'incidentClosed', primaryAction: 'open', canPollFast: false }
      : { label: 'paused', primaryAction: 'resume', canPollFast: false };
  }
  if (status === 'create_failed') {
    return { label: 'createFailed', primaryAction: 'retry', canPollFast: false };
  }
  if (status === 'degraded') {
    return { label: 'degraded', primaryAction: 'retry', canPollFast: false };
  }
  return syncingCount > 0
    ? { label: 'active', primaryAction: 'open', canPollFast: true, syncingCount }
    : { label: 'active', primaryAction: 'open', canPollFast: false };
};

export const getIMGroupPollDelay = (
  status: IncidentIMGroupStatus,
  elapsedMs: number,
  isPageVisible: boolean,
): number | null => {
  if (!isPageVisible || (status !== 'pending_create' && status !== 'creating')) {
    return null;
  }
  return elapsedMs < 30_000 ? 2_000 : 5_000;
};
