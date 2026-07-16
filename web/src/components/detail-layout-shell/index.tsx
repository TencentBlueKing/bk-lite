import React from 'react';
import WithSideMenuLayout from '@/components/layout/sub-layout';
import type { MenuItem } from '@/types';

interface DetailLayoutShellProps {
  topSection: React.ReactNode;
  intro?: React.ReactNode;
  onBackButtonClick: () => void;
  customMenuItems?: MenuItem[];
  showProgress?: boolean;
  taskProgressComponent?: React.ReactNode;
  children: React.ReactNode;
  wrapperClassName?: string;
}

const DetailLayoutShell: React.FC<DetailLayoutShellProps> = ({
  topSection,
  intro,
  onBackButtonClick,
  customMenuItems,
  showProgress,
  taskProgressComponent,
  children,
  wrapperClassName = 'w-full',
}) => {
  return (
    <div className={wrapperClassName}>
      <WithSideMenuLayout
        topSection={topSection}
        intro={intro}
        showBackButton={true}
        onBackButtonClick={onBackButtonClick}
        customMenuItems={customMenuItems}
        showProgress={showProgress}
        taskProgressComponent={taskProgressComponent}
      >
        {children}
      </WithSideMenuLayout>
    </div>
  );
};

export default DetailLayoutShell;
