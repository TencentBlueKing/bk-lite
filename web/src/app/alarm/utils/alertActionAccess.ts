export interface AlertActionAccessItem {
  status?: string;
  operator?: unknown;
}

export interface AlertActionAccessOptions {
  username?: string;
  isSuperUser?: boolean;
}

export const canReassignAlert = (
  item: AlertActionAccessItem,
  options: AlertActionAccessOptions
): boolean => {
  if (item.status === 'pending') {
    return Boolean(options.isSuperUser);
  }
  if (item.status === 'processing') {
    return Array.isArray(item.operator) && item.operator.includes(options.username);
  }
  return false;
};

export const alarmActionsForStatus = (
  status: string | undefined,
  options: AlertActionAccessOptions
): Array<'assign' | 'acknowledge' | 'reassign' | 'close'> => {
  if (status === 'unassigned') return ['assign'];
  if (status === 'pending') {
    return options.isSuperUser ? ['acknowledge', 'reassign'] : ['acknowledge'];
  }
  if (status === 'processing') return ['reassign', 'close'];
  return [];
};
