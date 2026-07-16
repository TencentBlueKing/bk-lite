import React from 'react';
import type { MenuItem } from '@/types';
import DetailLayoutShell from '@/components/detail-layout-shell';
import TopSection from '@/components/top-section';

export interface IntegrationDetailLayoutShellSummary {
  title?: React.ReactNode;
  description?: React.ReactNode;
  icon?: string | null;
}

interface IntegrationDetailLayoutShellProps {
  summary: IntegrationDetailLayoutShellSummary;
  menuItems?: MenuItem[];
  topSectionClassName?: string;
  onBackButtonClick: () => void;
  children: React.ReactNode;
}

const IntegrationDetailLayoutShell: React.FC<
  IntegrationDetailLayoutShellProps
> = ({
  summary,
  menuItems,
  topSectionClassName,
  onBackButtonClick,
  children,
}) => {
  return (
    <DetailLayoutShell
      topSection={
        <TopSection
          title={summary.title || ''}
          content={summary.description || ''}
          iconSrc={summary.icon ? `/assets/icons/${summary.icon}.svg` : undefined}
          iconAlt={typeof summary.title === 'string' ? summary.title : 'integration icon'}
          className={topSectionClassName}
          variant="integration"
        />
      }
      onBackButtonClick={onBackButtonClick}
      customMenuItems={menuItems}
    >
      {children}
    </DetailLayoutShell>
  );
};

export default IntegrationDetailLayoutShell;
