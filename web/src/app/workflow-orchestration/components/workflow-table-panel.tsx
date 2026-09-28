import type { ReactNode } from 'react';

import FilterToolbar from '@/components/filter-toolbar';

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
      <FilterToolbar align="between">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {filters}
        </div>
        {actions ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            {actions}
          </div>
        ) : null}
      </FilterToolbar>
      <div data-testid="workflow-table-scroll-region" className="min-h-0 flex-1 overflow-hidden">
        {children}
      </div>
    </section>
  );
}
