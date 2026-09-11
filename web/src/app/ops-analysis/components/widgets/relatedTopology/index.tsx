'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { HandledRequestError } from '@/utils/request';
import { useRelatedTopologyApi } from '@/app/ops-analysis/api/relatedTopology';
import WidgetErrorState from '@/app/ops-analysis/components/widgetErrorState';
import { buildRelatedTopologyGraph } from './graphModel';
import RelatedTopologyGraphView from './graphView';
import type { RelatedTopologyResponse } from './types';
import { RELATED_TOPOLOGY_CANVAS_STYLE } from './visual';

export interface RelatedTopologyProps {
  instUuid: string;
}

const RelatedTopology = ({ instUuid }: RelatedTopologyProps) => {
  const { t } = useTranslation();
  const { getRelatedTopology } = useRelatedTopologyApi();
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
        setError(caught.message || t('common.loadFailed'));
      } else {
        setError(t('common.loadFailed'));
      }
    } finally {
      setLoading(false);
    }
  }, [getRelatedTopology, instUuid, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const graph = useMemo(
    () => (payload ? buildRelatedTopologyGraph(payload) : null),
    [payload],
  );

  if (loading) {
    return (
      <div
        className="flex h-full min-h-[280px] items-center justify-center"
        style={RELATED_TOPOLOGY_CANVAS_STYLE}
      >
        <Spin />
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="flex h-full min-h-[280px] items-center justify-center"
        style={RELATED_TOPOLOGY_CANVAS_STYLE}
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
        style={RELATED_TOPOLOGY_CANVAS_STYLE}
      >
        <CompactEmptyState description={t('dashboard.relatedTopologyEmpty')} />
      </div>
    );
  }

  return (
    <div className="h-full min-h-[280px] min-w-0 w-full overflow-hidden">
      <RelatedTopologyGraphView model={graph} onRefresh={load} />
    </div>
  );
};

export default RelatedTopology;
