'use client';

import { useState } from 'react';
import Introduction from '@/app/cmdb/components/introduction';
import { useTranslation } from '@/utils/i18n';
import TaskTable from './components/taskTable';
import TaskWizard from './components/taskWizard';
import TaskDetail from './components/taskDetail';
import BatchReviewDrawer from './components/batchReviewDrawer';
import type { CustomReportingTask } from '@/app/cmdb/types/customReporting';

export default function CustomReportingPage() {
  const { t } = useTranslation();
  const [refreshToken, setRefreshToken] = useState(0);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<CustomReportingTask | null>(null);
  const [detailTask, setDetailTask] = useState<CustomReportingTask | null>(null);
  const [batchTask, setBatchTask] = useState<CustomReportingTask | null>(null);

  const openCreateWizard = () => {
    setEditingTask(null);
    setWizardOpen(true);
  };

  const openEditWizard = (task: CustomReportingTask) => {
    setEditingTask(task);
    setWizardOpen(true);
  };

  const closeWizard = () => {
    setWizardOpen(false);
    setEditingTask(null);
  };
  const closeDetail = () => setDetailTask(null);
  const closeBatch = () => setBatchTask(null);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      <div className="shrink-0">
        <Introduction
          title={t('CustomReporting.title')}
          message={t('CustomReporting.message')}
        />
      </div>
      <TaskTable
        refreshToken={refreshToken}
        onCreate={openCreateWizard}
        onEdit={openEditWizard}
        onView={(task) => setDetailTask(task)}
        onOpenBatchReview={(task) => setBatchTask(task)}
      />
      <TaskWizard
        open={wizardOpen}
        task={editingTask}
        onClose={closeWizard}
        onSaved={() => setRefreshToken((value) => value + 1)}
      />
      <TaskDetail
        open={Boolean(detailTask)}
        taskId={detailTask?.id}
        onClose={closeDetail}
        onEdit={(task) => {
          setDetailTask(task);
          openEditWizard(task);
        }}
        onOpenBatchReview={(task) => setBatchTask(task)}
      />
      <BatchReviewDrawer
        open={Boolean(batchTask)}
        task={batchTask}
        onClose={closeBatch}
      />
    </div>
  );
}
