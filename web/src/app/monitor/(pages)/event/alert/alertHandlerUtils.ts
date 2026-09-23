import {
  formatUserDisplayName,
  type UserDisplayItem
} from '@/utils/userDisplay';

export const hasAlertHandlers = (handlers: unknown): boolean =>
  Array.isArray(handlers) && handlers.length > 0;

export const isCurrentAlertHandler = (
  handlers: unknown,
  actor: { id?: unknown; username?: unknown }
): boolean => {
  if (!Array.isArray(handlers) || !handlers.length) {
    return false;
  }
  const candidates = new Set(
    [actor.id, actor.username]
      .filter((item) => item !== null && item !== undefined && item !== '')
      .map((item) => String(item))
  );
  return handlers.some((item) => candidates.has(String(item)));
};

export const canClaimOrAssignAlert = (
  status: unknown,
  handlers: unknown,
  activeStatus = 'new'
): boolean => status === activeStatus && !hasAlertHandlers(handlers);

export const canReassignAlert = (
  status: unknown,
  handlers: unknown,
  actor: { id?: unknown; username?: unknown },
  activeStatus = 'new'
): boolean =>
  status === activeStatus && isCurrentAlertHandler(handlers, actor);

export const canCloseAlert = (
  handlers: unknown,
  actor: { id?: unknown; username?: unknown }
): boolean => !hasAlertHandlers(handlers) || isCurrentAlertHandler(handlers, actor);

export const formatAlertHandlers = (
  handlers: unknown,
  handlersDisplay: unknown,
  userList: UserDisplayItem[] = []
): string => {
  if (Array.isArray(handlersDisplay) && handlersDisplay.length) {
    return handlersDisplay.filter(Boolean).join(',') || '--';
  }
  if (!Array.isArray(handlers) || !handlers.length) {
    return '--';
  }
  return (
    handlers
      .map((item) => formatUserDisplayName(item, userList))
      .join(',') || '--'
  );
};
