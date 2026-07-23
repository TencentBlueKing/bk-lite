import type {
  IncidentIMGroupOptions,
  IncidentIMMemberList,
  IncidentIMMemberListParams,
} from '@/app/alarm/types/incidents';

export interface PollScheduler {
  schedule: (callback: () => void, delay: number) => void;
  stop: () => void;
}

export interface PollTimerDependencies {
  setTimer: (callback: () => void, delay: number) => number;
  clearTimer: (timerId: number) => void;
}

export const createPollScheduler = ({ setTimer, clearTimer }: PollTimerDependencies): PollScheduler => {
  let timerId: number | null = null;
  const stop = () => {
    if (timerId !== null) {
      clearTimer(timerId);
      timerId = null;
    }
  };
  return {
    schedule: (callback, delay) => {
      stop();
      timerId = setTimer(() => {
        timerId = null;
        callback();
      }, delay);
    },
    stop,
  };
};

export const ownsIMGroupResponse = (
  currentIncidentPk: string,
  requestedIncidentPk: string,
  currentGroupId: string | null,
  requestedGroupId: string | null,
): boolean =>
  currentIncidentPk === requestedIncidentPk
  && currentGroupId === requestedGroupId;

export const getInitialMemberFilter = (
  pendingCount: number,
): IncidentIMMemberListParams['filter'] => pendingCount > 0 ? 'pending' : 'all';

export interface MemberQueryState {
  filter: IncidentIMMemberListParams['filter'];
  page: number;
  pageSize: 10 | 20 | 50 | 100;
}

export const resolveMemberQueryVisibility = (
  wasOpen: boolean,
  isOpen: boolean,
  current: MemberQueryState,
  pendingCount: number,
): MemberQueryState =>
  !wasOpen && isOpen
    ? { filter: getInitialMemberFilter(pendingCount), page: 1, pageSize: 20 }
    : current;

export const canSubmitIMGroupCreation = (
  options: IncidentIMGroupOptions | null,
  channelId?: number,
  groupName?: string,
  ownerUsername?: string,
): boolean =>
  Boolean(
    options?.channels.some(channel => channel.id === channelId)
    && groupName?.trim()
    && options?.owner_candidates?.some(owner => owner.username === ownerUsername),
  );

export const isChannelOptionsCurrent = (
  selectedChannelId: number | undefined,
  requestedChannelId: number,
): boolean => selectedChannelId === requestedChannelId;

export const shouldInitializeCreateForm = (
  wasOpen: boolean,
  isOpen: boolean,
): boolean => !wasOpen && isOpen;

export type RequestScope = 'group' | 'options' | 'members';

export interface RequestHandle {
  scope: RequestScope;
  generation: number;
  signal: AbortSignal;
}

export interface RequestGate {
  begin: (scope: RequestScope) => RequestHandle;
  isCurrent: (handle: RequestHandle) => boolean;
  finish: (handle: RequestHandle) => boolean;
  abort: (scope: RequestScope) => void;
  abortAll: () => void;
}

export const createRequestGate = (): RequestGate => {
  let generation = 0;
  const active = new Map<RequestScope, {
    generation: number;
    controller: AbortController;
  }>();
  const abort = (scope: RequestScope) => {
    active.get(scope)?.controller.abort();
    active.delete(scope);
  };
  return {
    begin: scope => {
      abort(scope);
      generation += 1;
      const controller = new AbortController();
      active.set(scope, { generation, controller });
      return { scope, generation, signal: controller.signal };
    },
    isCurrent: handle => {
      const current = active.get(handle.scope);
      return Boolean(
        current
        && current.generation === handle.generation
        && !handle.signal.aborted,
      );
    },
    finish: handle => {
      const current = active.get(handle.scope);
      if (
        !current
        || current.generation !== handle.generation
        || handle.signal.aborted
      ) return false;
      active.delete(handle.scope);
      return true;
    },
    abort,
    abortAll: () => {
      (['group', 'options', 'members'] as const).forEach(abort);
    },
  };
};

export interface CreatePermissionProbe {
  canCreate: boolean;
  options: IncidentIMGroupOptions | null;
  error: unknown | null;
}

export const probeCreatePermission = async (
  loadOptions: () => Promise<IncidentIMGroupOptions>,
): Promise<CreatePermissionProbe> => {
  try {
    const options = await loadOptions();
    return { canCreate: options.can_create, options, error: null };
  } catch (error) {
    return { canCreate: false, options: null, error };
  }
};

export interface MemberDrawerModel {
  data: IncidentIMMemberList;
  error: unknown | null;
}

export const settleMemberDrawerRequest = (
  _current: MemberDrawerModel,
  result: { data: IncidentIMMemberList } | { error: unknown },
): MemberDrawerModel => {
  return 'data' in result
    ? { data: result.data, error: null }
    : { data: { count: 0, items: [] }, error: result.error };
};

export const runIMGroupAction = async (
  action: () => Promise<void>,
  onSuccess: () => void,
  onError: (error: unknown) => void,
): Promise<boolean> => {
  try {
    await action();
    onSuccess();
    return true;
  } catch (error) {
    onError(error);
    return false;
  }
};
