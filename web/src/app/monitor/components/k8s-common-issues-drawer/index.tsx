import React, { forwardRef, useImperativeHandle, useState } from 'react';
import OperateFormDrawer from '@/components/operate-form-drawer';
import TroubleshootingCard from '@/components/troubleshooting-card';

export interface K8sCommonIssue {
  id: number;
  title: React.ReactNode;
  reason: React.ReactNode;
  solutions: React.ReactNode[];
}

export interface K8sCommonIssuesDrawerRef {
  showDrawer: () => void;
}

export interface K8sCommonIssuesDrawerProps {
  title: React.ReactNode;
  issues: K8sCommonIssue[];
  reasonLabel: React.ReactNode;
  solutionLabel: React.ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

const K8sCommonIssuesDrawer = forwardRef<
  K8sCommonIssuesDrawerRef,
  K8sCommonIssuesDrawerProps
>(({ title, issues, reasonLabel, solutionLabel, open, defaultOpen = false, onOpenChange }, ref) => {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);

  const mergedOpen = open ?? internalOpen;

  const setDrawerOpen = (nextOpen: boolean) => {
    if (open === undefined) {
      setInternalOpen(nextOpen);
    }
    onOpenChange?.(nextOpen);
  };

  useImperativeHandle(ref, () => ({
    showDrawer: () => setDrawerOpen(true),
  }));

  return (
    <OperateFormDrawer
      title={title}
      open={mergedOpen}
      onClose={() => setDrawerOpen(false)}
      hideFooter
      width={600}
    >
      <div className="space-y-4">
        {issues.map((issue) => (
          <TroubleshootingCard
            key={issue.id}
            badge={issue.id}
            title={issue.title}
            titleClassName="mb-2 text-base font-semibold"
            causeLabel={reasonLabel}
            cause={issue.reason}
            causeLayout="inline"
            solutionLabel={solutionLabel}
            solutions={issue.solutions}
            cardClassName="rounded-lg"
          />
        ))}
      </div>
    </OperateFormDrawer>
  );
});

K8sCommonIssuesDrawer.displayName = 'K8sCommonIssuesDrawer';

export default K8sCommonIssuesDrawer;
export type { K8sCommonIssuesPreset } from './presets';
export {
  createLogK8sCommonIssuesPreset,
  createMonitorK8sCommonIssuesPreset,
} from './presets';
