import type {
  IncidentIMGroupOptions,
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
  && (requestedGroupId === null || currentGroupId === requestedGroupId);

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
