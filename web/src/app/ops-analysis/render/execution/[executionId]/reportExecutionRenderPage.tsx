'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Spin } from 'antd';

import Report from '@/app/ops-analysis/(pages)/view/report';
import { useDashboardSubscriptionApi } from '@/app/ops-analysis/api/dashboardSubscription';
import { emitDashboardRenderSignal } from '@/app/ops-analysis/renderContract';
import type { DashboardExecutionRenderInput } from '@/app/ops-analysis/types/dashboardSubscription';
import type { FilterValue } from '@/app/ops-analysis/types/dashBoard';
import type { ReportDetail } from '@/app/ops-analysis/types/report';
import { collectWidgetManifestDataSourceIds } from '@/app/ops-analysis/utils/canvasResources';

interface ReportExecutionRenderPageContentProps {
  executionId: number;
  initialRenderInput?: DashboardExecutionRenderInput | null;
}

export const ReportExecutionRenderPageContent = ({
  executionId,
  initialRenderInput = null,
}: ReportExecutionRenderPageContentProps) => {
  const { getExecutionRenderInput } = useDashboardSubscriptionApi();
  const [renderInput, setRenderInput] =
    useState<DashboardExecutionRenderInput | null>(initialRenderInput);
  const failedRef = useRef(false);

  useEffect(() => {
    if (initialRenderInput) {
      setRenderInput(initialRenderInput);
      return;
    }
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
  }, [executionId, getExecutionRenderInput, initialRenderInput]);

  const reportDetail = useMemo<ReportDetail | null>(() => {
    if (!renderInput) return null;
    const snapshot = renderInput.render_snapshot;
    const reportId = snapshot.resource_id ?? executionId;
    return {
      id: reportId,
      name: snapshot.dashboard_name,
      updated_at: snapshot.dashboard_updated_at,
      view_sets: snapshot.view_sets,
      refresh_interval: 0,
    };
  }, [executionId, renderInput]);

  const getReportDetailOverride = useCallback(async () => {
    if (!reportDetail) {
      throw new Error('Render input is not ready');
    }
    return reportDetail;
  }, [reportDetail]);

  if (!renderInput || !reportDetail) {
    return <Spin fullscreen />;
  }

  const reportId = String(
    renderInput.render_snapshot.resource_id ?? executionId,
  );
  return (
    <Report
      selectedReport={{
        id: reportId,
        data_id: reportId,
        name: renderInput.render_snapshot.dashboard_name,
        type: 'report',
      }}
      renderMode
      renderFilterValues={
        renderInput.input_snapshot.filter_values as Record<string, FilterValue>
      }
      renderDataSourceIds={collectWidgetManifestDataSourceIds(
        renderInput.render_snapshot.widget_manifest,
      )}
      getReportDetailOverride={getReportDetailOverride}
    />
  );
};
