export const hasAlertHandlers = (handlers: unknown): boolean =>
  Array.isArray(handlers) && handlers.length > 0;

export const canClaimOrAssignAlert = (
  status: unknown,
  handlers: unknown,
  activeStatus = 'active'
): boolean => status === activeStatus && !hasAlertHandlers(handlers);

export const formatAlertHandlers = (
  handlers: unknown,
  handlersDisplay: unknown
): string => {
  if (Array.isArray(handlersDisplay) && handlersDisplay.length) {
    return handlersDisplay.filter(Boolean).join(', ') || '--';
  }
  if (!Array.isArray(handlers) || !handlers.length) {
    return '--';
  }
  return handlers.map((item) => String(item)).join(', ') || '--';
};
