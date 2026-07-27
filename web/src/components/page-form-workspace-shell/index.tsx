import React from 'react';
import PageFormHeaderCard from '@/components/page-form-header-card';
import WorkspacePanel from '@/components/workspace-panel';

export interface PageFormWorkspaceShellProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  onBackClick?: () => void;
  children: React.ReactNode;
  className?: string;
  headerSpacing?: 'default' | 'compact' | 'flush';
  panelClassName?: string;
}

const PageFormWorkspaceShell: React.FC<PageFormWorkspaceShellProps> = ({
  title,
  description,
  onBackClick,
  children,
  className = 'w-full h-full overflow-auto',
  headerSpacing = 'default',
  panelClassName,
}) => {
  return (
    <div className={className}>
      <PageFormHeaderCard
        title={title}
        description={description}
        onBackClick={onBackClick}
        spacing={headerSpacing}
      />

      <WorkspacePanel className={panelClassName}>
        {children}
      </WorkspacePanel>
    </div>
  );
};

export default PageFormWorkspaceShell;
