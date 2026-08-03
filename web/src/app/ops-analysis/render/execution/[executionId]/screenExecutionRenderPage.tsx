'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Spin } from 'antd';

import ScreenCanvas from '@/app/ops-analysis/(pages)/view/screen/components/screenCanvas';
import { normalizeScreenViewSets } from '@/app/ops-analysis/(pages)/view/screen/utils/viewport';
import { useDashboardSubscriptionApi } from '@/app/ops-analysis/api/dashboardSubscription';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import {
  buildDashboardRenderSignal,
  emitDashboardRenderSignal,
  type DashboardWidgetRenderResult,
} from '@/app/ops-analysis/renderContract';
import type { DashboardExecutionRenderInput } from '@/app/ops-analysis/types/dashboardSubscription';
import type { FilterValue } from '@/app/ops-analysis/types/dashBoard';
import { collectScreenDataSourceIds } from '@/app/ops-analysis/utils/canvasResources';

interface ScreenExecutionRenderPageContentProps {
  executionId: number;
  initialRenderInput?: DashboardExecutionRenderInput | null;
}

export const ScreenExecutionRenderPageContent = ({
  executionId,
  initialRenderInput = null,
}: ScreenExecutionRenderPageContentProps) => {
  const { getExecutionRenderInput } = useDashboardSubscriptionApi();
  const { loadCanvasDataSources, dataSources } = useDataSourceManager();
  const dataSourceResolver = useCallback(
    (dataSource?: string | number) => {
      if (dataSource == null || dataSource === '') return undefined;
      return dataSources.find(
        (item) => String(item.id) === String(dataSource),
      );
    },
    [dataSources],
  );
  const [renderInput, setRenderInput] =
    useState<DashboardExecutionRenderInput | null>(initialRenderInput);
  const [dataSourcesReady, setDataSourcesReady] = useState(false);
  const failedRef = useRef(false);
  const emittedRef = useRef(false);
  const renderResultsRef = useRef<Map<string, DashboardWidgetRenderResult>>(
    new Map(),
  );

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

  const viewSets = useMemo(() => {
    if (!renderInput) return null;
    return normalizeScreenViewSets(renderInput.render_snapshot.view_sets);
  }, [renderInput]);

  const widgetIds = useMemo(
    () => (viewSets?.items || []).map((item) => String(item.id)),
    [viewSets],
  );

  const filterValues = useMemo(() => {
    if (!renderInput) return {};
    return renderInput.input_snapshot.filter_values as Record<
      string,
      FilterValue
    >;
  }, [renderInput]);

  const tryEmitReady = useCallback(() => {
    if (emittedRef.current || failedRef.current || !dataSourcesReady) {
      return;
    }
    if (widgetIds.length === 0) {
      emittedRef.current = true;
      emitDashboardRenderSignal({
        type: 'report-ready',
        dashboardId: String(executionId),
        widgets: [],
      });
      return;
    }
    const signal = buildDashboardRenderSignal(
      executionId,
      widgetIds,
      renderResultsRef.current,
    );
    if (!signal) return;
    emittedRef.current = true;
    emitDashboardRenderSignal(signal);
  }, [dataSourcesReady, executionId, widgetIds]);

  const handleWidgetRenderStatus = useCallback(
    (result: DashboardWidgetRenderResult) => {
      if (emittedRef.current || failedRef.current) return;
      renderResultsRef.current.set(result.widgetId, result);
      tryEmitReady();
    },
    [tryEmitReady],
  );

  useEffect(() => {
    if (!viewSets) return;
    let cancelled = false;
    setDataSourcesReady(false);
    renderResultsRef.current = new Map();
    emittedRef.current = false;
    void loadCanvasDataSources(collectScreenDataSourceIds(viewSets))
      .then(() => {
        if (cancelled) return;
        setDataSourcesReady(true);
      })
      .catch(() => {
        if (cancelled || failedRef.current) return;
        failedRef.current = true;
        emitDashboardRenderSignal({
          type: 'report-failed',
          dashboardId: String(executionId),
          widgets: [],
          error: 'Screen datasource load failed',
          errorCode: 'datasource_missing',
        });
      });
    return () => {
      cancelled = true;
    };
  }, [executionId, loadCanvasDataSources, viewSets]);

  useEffect(() => {
    if (!dataSourcesReady) return;
    if (widgetIds.length > 0) {
      tryEmitReady();
      return;
    }
    // 无 widget：挂载后再给一帧 paint，避免早于 Canvas 呈现。
    let cancelled = false;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!cancelled) tryEmitReady();
      });
    });
    return () => {
      cancelled = true;
    };
  }, [dataSourcesReady, tryEmitReady, widgetIds.length]);

  if (!renderInput || !viewSets || !dataSourcesReady) {
    return <Spin fullscreen />;
  }

  const width = viewSets.viewport?.width || 1920;
  const height = viewSets.viewport?.height || 1080;

  return (
    <div
      className="overflow-hidden bg-slate-950"
      style={{ width, height }}
    >
      <ScreenCanvas
        viewSets={viewSets}
        fullscreen
        refreshVersion={0}
        screenId={
          renderInput.render_snapshot.resource_id ??
          renderInput.render_snapshot.dashboard_id ??
          undefined
        }
        dataSourceResolver={dataSourceResolver}
        onWidgetRenderStatus={handleWidgetRenderStatus}
        filterDefinitions={
          (renderInput.render_snapshot.filters as never[]) || []
        }
        unifiedFilterValues={filterValues}
        filterSearchVersion={0}
        namespaceSearchVersion={0}
      />
    </div>
  );
};
