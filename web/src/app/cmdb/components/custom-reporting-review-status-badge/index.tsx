import type { ReactNode } from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export type CustomReportingReviewStatus = 'pending' | 'approved' | 'rejected';

export interface CustomReportingReviewStatusBadgeProps {
  status: CustomReportingReviewStatus;
  label?: ReactNode;
  minWidth?: string | number;
}

const PALETTE_BY_STATUS: Record<
  CustomReportingReviewStatus,
  { textColor: string; backgroundColor: string }
> = {
  pending: {
    textColor: 'var(--color-warning)',
    backgroundColor: 'color-mix(in srgb, var(--color-warning) 12%, transparent)',
  },
  approved: {
    textColor: 'var(--color-success)',
    backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  rejected: {
    textColor: 'var(--color-error)',
    backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
  },
};

const CustomReportingReviewStatusBadge = ({
  status,
  label,
  minWidth,
}: CustomReportingReviewStatusBadgeProps) => {
  const palette = PALETTE_BY_STATUS[status];

  return (
    <StatusBadgeShell
      label={label}
      palette={palette}
      minWidth={minWidth}
    />
  );
};

export default CustomReportingReviewStatusBadge;
