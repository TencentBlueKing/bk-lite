import React from 'react';
import DetailLayoutShell from '@/components/detail-layout-shell';
import DetailIntro, { type DetailIntroProps } from '@/components/detail-intro';
import type { MenuItem } from '@/types';

export interface SummaryDetailLayoutShellProps {
  topSection: React.ReactNode;
  summary: DetailIntroProps;
  onBackButtonClick: () => void;
  customMenuItems?: MenuItem[];
  showProgress?: boolean;
  taskProgressComponent?: React.ReactNode;
  children: React.ReactNode;
  wrapperClassName?: string;
}

const SummaryDetailLayoutShell: React.FC<SummaryDetailLayoutShellProps> = ({
  topSection,
  summary,
  onBackButtonClick,
  customMenuItems,
  showProgress,
  taskProgressComponent,
  children,
  wrapperClassName,
}) => {
  return (
    <DetailLayoutShell
      topSection={topSection}
      intro={<DetailIntro {...summary} />}
      onBackButtonClick={onBackButtonClick}
      customMenuItems={customMenuItems}
      showProgress={showProgress}
      taskProgressComponent={taskProgressComponent}
      wrapperClassName={wrapperClassName}
    >
      {children}
    </DetailLayoutShell>
  );
};

export default SummaryDetailLayoutShell;
