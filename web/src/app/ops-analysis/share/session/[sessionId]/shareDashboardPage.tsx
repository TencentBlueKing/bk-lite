'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Spin } from 'antd';
import { useParams, useRouter } from 'next/navigation';
import Dashboard from '@/app/ops-analysis/(pages)/view/dashBoard';
import Topology from '@/app/ops-analysis/(pages)/view/topology';
import Architecture from '@/app/ops-analysis/(pages)/view/architecture';
import Screen from '@/app/ops-analysis/(pages)/view/screen';
import NetworkTopology from '@/app/ops-analysis/(pages)/view/networkTopology';
import { useCanvasShareApi } from '@/app/ops-analysis/api/dashboardShare';
import { ShareCanvasDetailProvider } from '@/app/ops-analysis/context/shareCanvasDetail';
import { ShareDataSourceProvider } from '@/app/ops-analysis/context/shareDataSource';
import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
import { ShareNetworkTopologyRuntimeProvider } from '@/app/ops-analysis/context/shareNetworkTopologyRuntime';
import { OpsAnalysisProvider } from '@/app/ops-analysis/context/common';
import { useTranslation } from '@/utils/i18n';
import type { DirItem } from '@/app/ops-analysis/types';
import type { SharedCanvasDto } from '@/app/ops-analysis/types/dashboardShare';
import type { NetworkTopologyConfig, NetworkTopologyLink } from '@/app/ops-analysis/types/networkTopology';

const DS_TYPES = new Set(['dashboard', 'topology', 'screen']);

export default function ShareDashboardPage() {
  const params = useParams<{ sessionId: string }>();
  const router = useRouter();
  const { t } = useTranslation();
  const api = useCanvasShareApi();
  const [canvas, setCanvas] = useState<SharedCanvasDto | null>(null);
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    if (!params.sessionId) return;
    api.getSharedCanvas(params.sessionId)
      .then(setCanvas)
      .catch(() => setInvalid(true));
  }, [api.getSharedCanvas, params.sessionId]);

  const selectedItem = useMemo<DirItem | null>(
    () =>
      canvas
        ? {
          id: `shared-${canvas.resource_type}-${canvas.id}`,
          data_id: String(canvas.id),
          name: canvas.name,
          desc: canvas.desc ?? '',
          type: canvas.resource_type,
          is_build_in: canvas.is_build_in,
        }
        : null,
    [canvas],
  );

  const getDetailOverride = useCallback(async () => canvas, [canvas]);
  const queryDataSource = useCallback(
    (dataSourceId: number, requestParams?: unknown) =>
      api.querySharedDataSource(params.sessionId, dataSourceId, requestParams),
    [api.querySharedDataSource, params.sessionId],
  );
  const shareAccess = useMemo(
    () => ({
      queryDataSource,
      getDataSourceDetails: () => api.getSharedDataSources(params.sessionId),
    }),
    [api.getSharedDataSources, params.sessionId, queryDataSource],
  );
  const networkTopologyRuntime = useMemo(
    () => ({
      getMetricValues: (
        items: Parameters<typeof api.getSharedNetworkTopologyMetricValues>[1],
      ) => api.getSharedNetworkTopologyMetricValues(params.sessionId, items),
      getLinkRuntime: (payload: {
        link: NetworkTopologyLink;
        nodes: NetworkTopologyConfig['nodes'];
      }) => api.getSharedNetworkTopologyLinkRuntime(params.sessionId, payload),
    }),
    [
      api.getSharedNetworkTopologyLinkRuntime,
      api.getSharedNetworkTopologyMetricValues,
      params.sessionId,
    ],
  );

  if (invalid) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-bg-1)] p-8">
        <div className="w-full max-w-[400px] text-center">
          <h2 className="mb-6 text-base font-medium text-[var(--color-text-1)]">
            {t('dashboard.shareInvalid')}
          </h2>
          <Button type="primary" onClick={() => router.push('/')}>
            {t('common.backToHome')}
          </Button>
        </div>
      </div>
    );
  }
  if (!canvas || !selectedItem) {
    return <Spin fullscreen tip={t('dashboard.shareLoading')} />;
  }

  // 第一阶段不渲染 report：页面未完成，避免分享态进入占位页。
  if (canvas.resource_type === 'report') {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-bg-1)] p-8">
        <div className="w-full max-w-[400px] text-center">
          <h2 className="mb-6 text-base font-medium text-[var(--color-text-1)]">
            {t('dashboard.shareInvalid')}
          </h2>
          <Button type="primary" onClick={() => router.push('/')}>
            {t('common.backToHome')}
          </Button>
        </div>
      </div>
    );
  }

  const content = (() => {
    switch (canvas.resource_type) {
      case 'dashboard':
        return (
          <Dashboard
            selectedDashboard={selectedItem}
            shareMode
            shareSessionId={params.sessionId}
            getDashboardDetailOverride={getDetailOverride}
          />
        );
      case 'topology':
        return <Topology selectedTopology={selectedItem} shareMode />;
      case 'architecture':
        return <Architecture selectedArchitecture={selectedItem} shareMode />;
      case 'screen':
        return <Screen selectedScreen={selectedItem} shareMode />;
      case 'networkTopology':
        return (
          <NetworkTopology
            selectedNetworkTopology={selectedItem}
            shareMode
          />
        );
      default:
        return null;
    }
  })();

  let body = (
    <ShareCanvasDetailProvider value={getDetailOverride}>
      <ShareModeProvider value>
        <OpsAnalysisProvider>
          <main className="h-full w-full overflow-hidden">{content}</main>
        </OpsAnalysisProvider>
      </ShareModeProvider>
    </ShareCanvasDetailProvider>
  );

  if (DS_TYPES.has(canvas.resource_type)) {
    body = <ShareDataSourceProvider value={shareAccess}>{body}</ShareDataSourceProvider>;
  }
  if (canvas.resource_type === 'networkTopology') {
    body = (
      <ShareNetworkTopologyRuntimeProvider value={networkTopologyRuntime}>
        {body}
      </ShareNetworkTopologyRuntimeProvider>
    );
  }

  return body;
}
