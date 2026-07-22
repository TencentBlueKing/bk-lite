import React, { useMemo } from 'react';
import DetailLayoutShell from '@/components/detail-layout-shell';
import TopSection from '@/components/top-section';
import type { MenuItem } from '@/types';

export interface RoutedDetailLayoutShellItem {
  path: string;
  title: string;
  description: string;
}

interface RoutedDetailLayoutShellProps {
  pathname: string | null;
  items: RoutedDetailLayoutShellItem[];
  fallback: {
    title: string;
    description: string;
  };
  intro?: React.ReactNode;
  onBackButtonClick: () => void;
  customMenuItems?: MenuItem[];
  showProgress?: boolean;
  taskProgressComponent?: React.ReactNode;
  children: React.ReactNode;
  wrapperClassName?: string;
}

const RoutedDetailLayoutShell: React.FC<RoutedDetailLayoutShellProps> = ({
  pathname,
  items,
  fallback,
  intro,
  onBackButtonClick,
  customMenuItems,
  showProgress,
  taskProgressComponent,
  children,
  wrapperClassName,
}) => {
  const currentItem = useMemo(() => {
    return items.find((item) => item.path === pathname);
  }, [items, pathname]);

  return (
    <DetailLayoutShell
      topSection={
        <TopSection
          title={currentItem?.title || fallback.title}
          content={currentItem?.description || fallback.description}
        />
      }
      intro={intro}
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

export default RoutedDetailLayoutShell;
