import type { ReactNode } from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export type CustomReportingTaskRuntimeStatus =
  | 'receiving'
  | 'pending_review'
  | 'no_report';

export type CustomReportingBatchRuntimeStatus =
  | 'running'
  | 'success'
  | 'failed';

interface CustomReportingRuntimeStatusConfig {
  textColor: string;
  backgroundColor: string;
}

const TASK_STATUS_PALETTE: Record<
  CustomReportingTaskRuntimeStatus,
  CustomReportingRuntimeStatusConfig
> = {
  receiving: {
    textColor: 'var(--color-success)',
    backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  pending_review: {
    textColor: 'var(--color-warning)',
    backgroundColor: 'color-mix(in srgb, var(--color-warning) 12%, transparent)',
  },
  no_report: {
    textColor: 'var(--color-text-3)',
    backgroundColor: 'color-mix(in srgb, var(--color-fill-5) 32%, transparent)',
  },
};

const BATCH_STATUS_PALETTE: Record<
  CustomReportingBatchRuntimeStatus,
  CustomReportingRuntimeStatusConfig
> = {
  running: {
    textColor: 'var(--color-primary)',
    backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  success: {
    textColor: 'var(--color-success)',
    backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  failed: {
    textColor: 'var(--color-error)',
    backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
  },
};

interface TaskProps {
  kind: 'task';
  status: CustomReportingTaskRuntimeStatus;
  label?: ReactNode;
  minWidth?: string | number;
}

interface BatchProps {
  kind: 'batch';
  status: CustomReportingBatchRuntimeStatus;
  label?: ReactNode;
  minWidth?: string | number;
}

export type CustomReportingRuntimeStatusBadgeProps = TaskProps | BatchProps;

const CustomReportingRuntimeStatusBadge = ({
  kind,
  status,
  label,
  minWidth,
}: CustomReportingRuntimeStatusBadgeProps) => {
  const palette =
    kind === 'task'
      ? TASK_STATUS_PALETTE[status]
      : BATCH_STATUS_PALETTE[status];

  return (
    <StatusBadgeShell
      label={label}
      palette={palette}
      minWidth={minWidth}
    />
  );
};

export default CustomReportingRuntimeStatusBadge;
