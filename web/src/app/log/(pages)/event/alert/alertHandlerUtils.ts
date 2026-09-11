import {
  formatUserDisplayName,
  type UserDisplayItem
} from '@/utils/userDisplay';

export const hasAlertHandlers = (handlers: unknown): boolean =>
  Array.isArray(handlers) && handlers.length > 0;

export const isLogHitEvent = (item: {
  action?: string | null;
  [key: string]: unknown;
}): boolean => !item.action;

export const canClaimOrAssignAlert = (
  status: unknown,
  handlers: unknown,
  activeStatus = 'new'
): boolean => status === activeStatus && !hasAlertHandlers(handlers);

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
