import type { ReactNode } from 'react';

import ToolbarSplitShell from '@/components/toolbar-split-shell';

interface WorkflowTablePanelProps {
  filters: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

export function WorkflowTablePanel({ filters, actions, children }: WorkflowTablePanelProps) {
  return (
    <section
      data-testid="workflow-table-panel"
      className="flex min-h-0 flex-1 flex-col"
    >
      <ToolbarSplitShell
        trailing={(
          <>
            {filters}
            {actions}
          </>
        )}
      />
      <div data-testid="workflow-table-scroll-region" className="min-h-0 flex-1 overflow-hidden">
        {children}
      </div>
    </section>
  );
}
