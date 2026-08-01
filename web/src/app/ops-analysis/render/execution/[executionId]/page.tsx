'use client';

import { useParams } from 'next/navigation';

import { DashboardRenderOpsAnalysisProvider } from '@/app/ops-analysis/context/common';
import { DashboardExecutionRenderPageContent } from './dashboardExecutionRenderPage';

export default function DashboardExecutionRenderPage() {
  const params = useParams<{ executionId: string }>();
  const executionId = Number(params.executionId);

  return (
    <DashboardRenderOpsAnalysisProvider>
      <DashboardExecutionRenderPageContent executionId={executionId} />
    </DashboardRenderOpsAnalysisProvider>
  );
}
