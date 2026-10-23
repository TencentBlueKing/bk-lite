'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Spin } from 'antd';
import { useParams } from 'next/navigation';
import CompactEmptyState from '@/components/compact-empty-state';
import { useShareMode } from '@/app/ops-analysis/context/shareMode';
import { useApplicationTopologyApi } from '@/app/ops-analysis/api/applicationTopology';
import WidgetErrorState from '@/app/ops-analysis/components/widgetErrorState';
import { applicationTopologySurfaceStyle } from './graphView';
import { APPLICATION_TOPOLOGY_DEFAULT_DEPTH } from '@/app/ops-analysis/types/sceneWidget';
import { isScreenChartThemeMode, type OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { HandledRequestError } from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import ApplicationTopologyGraphView from './graphView';
import type { ScreenRenderContext, ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type { ApplicationTopologyResponse } from './types';

export interface ApplicationTopologyProps {
  instUuid: string;
  depth?: number;
  config?: ValueConfig;
  chartThemeMode?: OpsChartThemeMode;
  screenRenderContext?: ScreenRenderContext;
}

const ApplicationTopology = ({
  instUuid,
  depth = APPLICATION_TOPOLOGY_DEFAULT_DEPTH,
  config,
  chartThemeMode,
  screenRenderContext,
}: ApplicationTopologyProps) => {
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;
  const usesScreenTheme = isScreenChartThemeMode(chartThemeMode);
  const canvasStyle = applicationTopologySurfaceStyle(usesScreenTheme);
  const shareMode = useShareMode();
  const params = useParams<{ sessionId?: string }>();
  const { getApplicationTopology } = useApplicationTopologyApi(
    shareMode ? params.sessionId : undefined,
  );
  const [loading, setLoading] = useState(true);
  const [payload, setPayload] = useState<ApplicationTopologyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getApplicationTopology(instUuid, depth);
      setPayload(data);
    } catch (caught) {
      setPayload(null);
      if (caught instanceof HandledRequestError) {
        setError(caught.message || tRef.current('dashboard.applicationTopologyLoadFailed'));
      } else {
        setError(tRef.current('dashboard.applicationTopologyLoadFailed'));
      }
    } finally {
      setLoading(false);
    }
  }, [depth, getApplicationTopology, instUuid]);

  useEffect(() => {
    void load();
  }, [load]);

  const nodes = useMemo(() => payload?.nodes || [], [payload]);

  if (loading) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center" style={canvasStyle}>
        <Spin />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center" style={canvasStyle}>
        <div className="flex flex-col items-center gap-3">
          <WidgetErrorState message={error} />
          <Button onClick={() => void load()}>{t('dashboard.applicationTopologyRetry')}</Button>
        </div>
      </div>
    );
  }

  if (!payload?.center?.id || nodes.length === 0) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center" style={canvasStyle}>
        <CompactEmptyState description={t('dashboard.applicationTopologyEmpty')} />
      </div>
    );
  }

  return (
    <div className="h-full min-h-[280px] min-w-0 w-full overflow-hidden">
      <ApplicationTopologyGraphView
        centerId={payload.center_inst_uuid || payload.center.id}
        nodes={nodes}
        links={payload.links || []}
        usesScreenTheme={usesScreenTheme}
        chartThemeMode={chartThemeMode}
        shareMode={Boolean(shareMode)}
        config={config}
        screenScaleX={screenRenderContext?.scaleX}
        screenScaleY={screenRenderContext?.scaleY}
        onRefresh={() => void load()}
      />
    </div>
  );
};

export default ApplicationTopology;
