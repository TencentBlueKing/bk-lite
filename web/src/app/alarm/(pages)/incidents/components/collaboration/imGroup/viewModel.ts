import type {
  IncidentIMGroup,
  IncidentIMGroupOptions,
  IncidentIMOwnerCandidate,
} from '@/app/alarm/types/incidents';
import { deriveIMGroupView } from './state';

export const PANEL_SIDEBAR_WIDTH_CLASS = 'w-full lg:w-[220px]';

interface CreateModalModelInput {
  selectedChannelId?: number;
  resolvedChannelId?: number;
  options: IncidentIMGroupOptions | null;
  previewError: unknown | null;
}

export interface CreateModalModel {
  contextual: boolean;
  ownerCandidates: IncidentIMOwnerCandidate[];
  defaultOwnerUsername: string | null;
  showPreviewError: boolean;
  canCreate: boolean;
}

export const deriveCreateModalModel = ({
  selectedChannelId,
  resolvedChannelId,
  options,
  previewError,
}: CreateModalModelInput): CreateModalModel => {
  const contextual = selectedChannelId !== undefined
    && resolvedChannelId === selectedChannelId
    && options !== null;
  const ownerCandidates = contextual ? options.owner_candidates ?? [] : [];
  const preferred = contextual ? options.preferred_owner_username : null;
  const preferredIsCandidate = ownerCandidates.some(
    candidate => candidate.username === preferred,
  );
  return {
    contextual,
    ownerCandidates,
    defaultOwnerUsername: preferredIsCandidate
      ? preferred
      : ownerCandidates[0]?.username ?? null,
    showPreviewError: Boolean(previewError),
    canCreate: Boolean(contextual && options.can_create && ownerCandidates.length > 0),
  };
};

export type MemberDrawerPhase = 'progress' | 'members';

export interface MemberDrawerViewModel {
  phase: MemberDrawerPhase;
  statusLabel: ReturnType<typeof deriveIMGroupView>['label'];
  continuousSyncEnabled: boolean;
  lastSyncAt: string | null;
  showMemberError: boolean;
  canRetryPending: boolean;
  showMappingRepair: boolean;
}

export const deriveMemberDrawerModel = (
  group: IncidentIMGroup,
  memberError: unknown | null,
): MemberDrawerViewModel => {
  const phase: MemberDrawerPhase = [
    'pending_create',
    'creating',
    'create_failed',
  ].includes(group.status) ? 'progress' : 'members';
  const pendingCount = group.member_summary.total - group.member_summary.joined;
  return {
    phase,
    statusLabel: deriveIMGroupView(group).label,
    continuousSyncEnabled: group.continuous_sync_enabled,
    lastSyncAt: group.last_sync_at,
    showMemberError: phase === 'members' && Boolean(memberError),
    canRetryPending: phase === 'members'
      && group.permissions.can_retry
      && pendingCount > 0,
    showMappingRepair: phase === 'members'
      && (group.member_summary.unmapped + group.member_summary.conflict > 0),
  };
};

export type PanelState = 'loading' | 'group-error' | 'permission-error' | 'empty' | 'group';

interface PanelModelInput {
  group: IncidentIMGroup | null;
  groupLoading: boolean;
  groupError: boolean;
  optionsLoading: boolean;
  optionsError: unknown | null;
  options: IncidentIMGroupOptions | null;
}

export interface PanelViewModel {
  state: PanelState;
  canCreate: boolean;
  showPermissionError: boolean;
  primaryAction: ReturnType<typeof deriveIMGroupView>['primaryAction'] | null;
  sidebarClassName: typeof PANEL_SIDEBAR_WIDTH_CLASS;
}

export const derivePanelModel = ({
  group,
  groupLoading,
  groupError,
  optionsLoading,
  optionsError,
  options,
}: PanelModelInput): PanelViewModel => {
  let state: PanelState;
  if (group) state = 'group';
  else if (groupLoading || optionsLoading || (!options && !groupError && !optionsError)) state = 'loading';
  else if (groupError) state = 'group-error';
  else if (optionsError) state = 'permission-error';
  else state = 'empty';
  return {
    state,
    canCreate: Boolean(options?.can_create),
    showPermissionError: state === 'permission-error',
    primaryAction: group ? deriveIMGroupView(group).primaryAction : null,
    sidebarClassName: PANEL_SIDEBAR_WIDTH_CLASS,
  };
};
