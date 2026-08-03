'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Spin } from 'antd';

import Dashboard from '@/app/ops-analysis/(pages)/view/dashBoard';
import { useDashboardSubscriptionApi } from '@/app/ops-analysis/api/dashboardSubscription';
import { emitDashboardRenderSignal } from '@/app/ops-analysis/renderContract';
import type { DashboardExecutionRenderInput } from '@/app/ops-analysis/types/dashboardSubscription';
import type { FilterValue } from '@/app/ops-analysis/types/dashBoard';

interface DashboardExecutionRenderPageContentProps {
  executionId: number;
}

export const DashboardExecutionRenderPageContent = ({
  executionId,
}: DashboardExecutionRenderPageContentProps) => {
  const { getExecutionRenderInput } = useDashboardSubscriptionApi();
  const [renderInput, setRenderInput] =
    useState<DashboardExecutionRenderInput | null>(null);
  const failedRef = useRef(false);

  useEffect(() => {
    let active = true;
    getExecutionRenderInput(executionId)
      .then((input) => {
        if (active) setRenderInput(input);
      })
      .catch(() => {
        if (!active || failedRef.current) return;
        failedRef.current = true;
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

  const dashboardDetail = useMemo(() => {
    if (!renderInput) return null;
    const snapshot = renderInput.render_snapshot;
    return {
      id: snapshot.dashboard_id,
      name: snapshot.dashboard_name,
      updated_at: snapshot.dashboard_updated_at,
      view_sets: snapshot.view_sets,
      filters: snapshot.filters,
      other: snapshot.other,
    };
  }, [renderInput]);

  const getDashboardDetailOverride = useCallback(async () => {
    if (!dashboardDetail) {
      throw new Error('Render input is not ready');
    }
    return dashboardDetail;
  }, [dashboardDetail]);

  if (!renderInput || !dashboardDetail) {
    return <Spin fullscreen />;
  }

  const dashboardId = String(renderInput.render_snapshot.dashboard_id);
  return (
    <Dashboard
      selectedDashboard={{
        id: dashboardId,
        data_id: dashboardId,
        name: renderInput.render_snapshot.dashboard_name,
        type: 'dashboard',
      }}
      renderMode
      renderFilterValues={
        renderInput.input_snapshot.filter_values as Record<string, FilterValue>
      }
      getDashboardDetailOverride={getDashboardDetailOverride}
    />
  );
};
