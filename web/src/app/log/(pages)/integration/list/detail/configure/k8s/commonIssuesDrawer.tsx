import React, { forwardRef, useImperativeHandle, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import OperateDrawer from '@/components/operate-drawer';

interface DrawerRef {
  showDrawer: () => void;
}

const CommonIssuesDrawer = forwardRef<DrawerRef>((_, ref) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  useImperativeHandle(ref, () => ({
    showDrawer: () => setOpen(true),
  }));

  const issues = [
    {
      id: 1,
      title: t('log.integration.k8s.commonIssuePendingTitle'),
      reason: t('log.integration.k8s.commonIssuePendingReason'),
      solutions: [
        t('log.integration.k8s.commonIssuePendingSolution1'),
        t('log.integration.k8s.commonIssuePendingSolution2'),
      ],
    },
    {
      id: 2,
      title: t('log.integration.k8s.commonIssueNatsTitle'),
      reason: t('log.integration.k8s.commonIssueNatsReason'),
      solutions: [
        t('log.integration.k8s.commonIssueNatsSolution1'),
        t('log.integration.k8s.commonIssueNatsSolution2'),
      ],
    },
    {
      id: 3,
      title: t('log.integration.k8s.commonIssueMountTitle'),
      reason: t('log.integration.k8s.commonIssueMountReason'),
      solutions: [
        t('log.integration.k8s.commonIssueMountSolution1'),
        t('log.integration.k8s.commonIssueMountSolution2'),
      ],
    },
  ];

  return (
    <OperateDrawer
      title={t('log.integration.k8s.commonIssues')}
      open={open}
      onClose={() => setOpen(false)}
      width={600}
    >
      <div className="space-y-4">
        {issues.map((issue) => (
          <div key={issue.id} className="bg-[var(--color-fill-1)] p-4 rounded-lg">
            <div className="flex items-start mb-3">
              <div className="bg-[var(--color-primary)] text-white rounded-full w-6 h-6 flex items-center justify-center text-sm font-bold mr-3 flex-shrink-0">
                {issue.id}
              </div>
              <div className="flex-1">
                <h4 className="text-base font-semibold mb-2">{issue.title}</h4>
                <div className="text-sm text-[var(--color-text-3)] mb-3">
                  <span className="font-medium">{t('log.integration.k8s.reasonLabel')}</span>
                  {issue.reason}
                </div>
                <div className="text-sm">
                  <div className="font-medium text-[var(--color-text-2)] mb-2">
                    {t('log.integration.k8s.solutionLabel')}
                  </div>
                  <ul className="space-y-1 pl-4">
                    {issue.solutions.map((solution, index) => (
                      <li
                        key={index}
                        className="text-[var(--color-text-3)] flex items-start"
                      >
                        <span className="mr-2">•</span>
                        <span>{solution}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </OperateDrawer>
  );
});

CommonIssuesDrawer.displayName = 'CommonIssuesDrawer';

export default CommonIssuesDrawer;
