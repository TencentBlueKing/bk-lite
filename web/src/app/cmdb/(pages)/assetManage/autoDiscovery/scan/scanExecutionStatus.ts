export const SCAN_ACTIVE_STATUSES = ['pending', 'running', 'finalizing'] as const;

const SCAN_ACTIVE_STATUS_SET = new Set<string>(SCAN_ACTIVE_STATUSES);

export const isScanExecutionBusy = (status?: string | null): boolean =>
  Boolean(status && SCAN_ACTIVE_STATUS_SET.has(status));

export const isScanExecuteDisabled = ({
  taskId,
  executingTaskId,
  executionStatus,
}: {
  taskId: number;
  executingTaskId: number | null;
  executionStatus?: string | null;
}): boolean => {
  if (isScanExecutionBusy(executionStatus)) {
    return true;
  }
  return executingTaskId !== null && executingTaskId !== taskId;
};
