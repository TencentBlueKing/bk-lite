import React from 'react';
import { PlusOutlined } from '@ant-design/icons';

export interface OpsAnalysisDashboardEmptyStateProps {
  description: React.ReactNode;
  action?: React.ReactNode;
}

const OpsAnalysisDashboardEmptyState: React.FC<OpsAnalysisDashboardEmptyStateProps> = ({
  description,
  action,
}) => {
  return (
    <div className="flex h-full flex-col items-center justify-center px-4 py-8 text-center">
      <div className="w-full max-w-[320px] rounded-[8px] border border-[var(--color-border)] bg-[var(--color-bg-1)] px-6 py-7 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
        <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[rgba(47,107,255,0.08)] text-[var(--color-primary)]">
          <PlusOutlined aria-hidden="true" style={{ fontSize: 18 }} />
        </div>
        <div className="text-sm leading-6 text-[var(--color-text-2)]">
          {description}
        </div>
        {action ? (
          <div className="mt-5 flex justify-center">
            {action}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default OpsAnalysisDashboardEmptyState;
