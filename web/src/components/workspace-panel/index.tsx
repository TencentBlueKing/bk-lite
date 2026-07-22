import React from 'react';

export interface WorkspacePanelProps {
  children: React.ReactNode;
  toolbar?: React.ReactNode;
  className?: string;
}

const WorkspacePanel: React.FC<WorkspacePanelProps> = ({
  children,
  toolbar,
  className = '',
}) => {
  return (
    <div
      className={`rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-6 py-6 ${className}`}
    >
      {toolbar ? <div className="mb-4 shrink-0">{toolbar}</div> : null}
      {children}
    </div>
  );
};

export default WorkspacePanel;
