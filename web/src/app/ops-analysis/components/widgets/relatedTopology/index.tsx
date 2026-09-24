'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { HandledRequestError } from '@/utils/request';
import { useShareMode } from '@/app/ops-analysis/context/shareMode';
import { useRelatedTopologyApi } from '@/app/ops-analysis/api/relatedTopology';
import WidgetErrorState from '@/app/ops-analysis/components/widgetErrorState';
import { buildRelatedTopologyGraph } from './graphModel';
import RelatedTopologyGraphView from './graphView';
import type { RelatedTopologyResponse } from './types';
import { isScreenChartThemeMode, type OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { relatedTopologyCanvasStyle } from './visual';

export interface RelatedTopologyProps {
  instUuid: string;
  chartThemeMode?: OpsChartThemeMode;
}

const RelatedTopology = ({ instUuid, chartThemeMode }: RelatedTopologyProps) => {
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;
  const usesScreenTheme = isScreenChartThemeMode(chartThemeMode);
  const canvasStyle = relatedTopologyCanvasStyle(usesScreenTheme);
  const shareMode = useShareMode();
  const params = useParams<{ sessionId?: string }>();
  const { getRelatedTopology } = useRelatedTopologyApi(
    shareMode ? params.sessionId : undefined,
  );
  const [loading, setLoading] = useState(true);
  const [payload, setPayload] = useState<RelatedTopologyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRelatedTopology(instUuid);
      setPayload(data);
    } catch (caught) {
      setPayload(null);
      if (caught instanceof HandledRequestError) {
        setError(caught.message || tRef.current('common.loadFailed'));
      } else {
        setError(tRef.current('common.loadFailed'));
      }
    } finally {
      setLoading(false);
    }
  }, [getRelatedTopology, instUuid]);

  useEffect(() => {
    void load();
  }, [load]);

  const graph = useMemo(
    () => (payload ? buildRelatedTopologyGraph(payload, t) : null),
    [payload, t],
  );

  if (loading) {
    return (
      <div
        className="flex h-full min-h-[280px] items-center justify-center"
        style={canvasStyle}
      >
        <Spin />
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="flex h-full min-h-[280px] items-center justify-center"
        style={canvasStyle}
      >
        <WidgetErrorState
          message={error || t('dashboard.relatedTopologyLoadFailed')}
        />
      </div>
    );
  }

  if (!graph || graph.empty) {
    return (
      <div
        className="flex h-full min-h-[280px] items-center justify-center"
        style={canvasStyle}
      >
        <CompactEmptyState description={t('dashboard.relatedTopologyEmpty')} />
      </div>
    );
  }

  return (
    <div className="h-full min-h-[280px] min-w-0 w-full overflow-hidden">
      <RelatedTopologyGraphView
        model={graph}
        chartThemeMode={chartThemeMode}
        onRefresh={load}
      />
    </div>
  );
};

export default RelatedTopology;
