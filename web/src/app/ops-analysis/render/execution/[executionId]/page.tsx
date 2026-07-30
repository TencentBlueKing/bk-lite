'use client';

import { useParams } from 'next/navigation';

import { OpsAnalysisProvider } from '@/app/ops-analysis/context/common';
import { DashboardExecutionRenderPageContent } from './dashboardExecutionRenderPage';

export default function DashboardExecutionRenderPage() {
  const params = useParams<{ executionId: string }>();
  const executionId = Number(params.executionId);

  return (
    <OpsAnalysisProvider>
      <DashboardExecutionRenderPageContent executionId={executionId} />
    </OpsAnalysisProvider>
  );
}
