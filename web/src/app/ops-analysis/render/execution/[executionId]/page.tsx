'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Spin } from 'antd';

import { DashboardRenderOpsAnalysisProvider } from '@/app/ops-analysis/context/common';
import { useDashboardSubscriptionApi } from '@/app/ops-analysis/api/dashboardSubscription';
import { emitDashboardRenderSignal } from '@/app/ops-analysis/renderContract';
import type { DashboardExecutionRenderInput } from '@/app/ops-analysis/types/dashboardSubscription';
import { DashboardExecutionRenderPageContent } from './dashboardExecutionRenderPage';
import { ScreenExecutionRenderPageContent } from './screenExecutionRenderPage';

export default function DashboardExecutionRenderPage() {
  const params = useParams<{ executionId: string }>();
  const executionId = Number(params.executionId);
  const { getExecutionRenderInput } = useDashboardSubscriptionApi();
  const [renderInput, setRenderInput] =
    useState<DashboardExecutionRenderInput | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    getExecutionRenderInput(executionId)
      .then((input) => {
        if (active) setRenderInput(input);
      })
      .catch(() => {
        if (!active) return;
        setFailed(true);
        emitDashboardRenderSignal({
          type: 'report-failed',
          dashboardId: String(executionId),
          widgets: [],
          error: 'Render input load failed',
        });
      });
    return () => {
      active = false;
    };
  }, [executionId, getExecutionRenderInput]);

  if (failed) {
    return null;
  }

  if (!renderInput) {
    return (
      <DashboardRenderOpsAnalysisProvider>
        <Spin fullscreen />
      </DashboardRenderOpsAnalysisProvider>
    );
  }

  const resourceType = renderInput.render_snapshot.resource_type || 'dashboard';

  return (
    <DashboardRenderOpsAnalysisProvider>
      {resourceType === 'screen' ? (
        <ScreenExecutionRenderPageContent
          executionId={executionId}
          initialRenderInput={renderInput}
        />
      ) : (
        <DashboardExecutionRenderPageContent executionId={executionId} />
      )}
    </DashboardRenderOpsAnalysisProvider>
  );
}
