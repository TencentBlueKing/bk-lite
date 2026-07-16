import { Space } from 'antd';
import type { CustomReportingReviewStatusSummary as ReviewStatusSummary } from '@/components/custom-reporting-shared/types';
import CustomReportingReviewStatusBadge from '@/components/custom-reporting-review-status-badge';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';

export interface CustomReportingReviewStatusSummaryProps {
  summary?: Partial<ReviewStatusSummary> | null;
  className?: string;
}

const CustomReportingReviewStatusSummary = ({
  summary,
  className,
}: CustomReportingReviewStatusSummaryProps) => {
  const { t } = useTranslation();
  const resolvedSummary = {
    pending: summary?.pending ?? 0,
    approved: summary?.approved ?? 0,
    rejected: summary?.rejected ?? 0,
    total: summary?.total ?? 0,
  };

  return (
    <div className={className}>
      <Space wrap>
        <CustomReportingReviewStatusBadge
          status="pending"
          label={`${t('CustomReporting.statusLabel.pending')}: ${resolvedSummary.pending}`}
        />
        <CustomReportingReviewStatusBadge
          status="approved"
          label={`${t('CustomReporting.statusLabel.approved')}: ${resolvedSummary.approved}`}
        />
        <CustomReportingReviewStatusBadge
          status="rejected"
          label={`${t('CustomReporting.statusLabel.rejected')}: ${resolvedSummary.rejected}`}
        />
        <StatusBadgeShell
          label={`${t('CustomReporting.totalCount')}: ${resolvedSummary.total}`}
          palette={{
            textColor: 'var(--color-text-2)',
            backgroundColor:
              'color-mix(in srgb, var(--color-fill-5) 32%, transparent)',
          }}
        />
      </Space>
    </div>
  );
};

export default CustomReportingReviewStatusSummary;
