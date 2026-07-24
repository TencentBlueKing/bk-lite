'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Spin } from 'antd';
import { useParams, useRouter } from 'next/navigation';
import Dashboard from '@/app/ops-analysis/(pages)/view/dashBoard';
import { useDashboardShareApi } from '@/app/ops-analysis/api/dashboardShare';
import { ShareDataSourceProvider } from '@/app/ops-analysis/context/shareDataSource';
import { OpsAnalysisProvider } from '@/app/ops-analysis/context/common';
import type { DirItem } from '@/app/ops-analysis/types';
import type { SharedDashboardDto } from '@/app/ops-analysis/types/dashboardShare';

export default function ShareDashboardPage() {
  const params = useParams<{ sessionId: string }>();
  const router = useRouter();
  const api = useDashboardShareApi();
  const [dashboard, setDashboard] = useState<SharedDashboardDto | null>(null);
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    if (!params.sessionId) return;
    api.getSharedDashboard(params.sessionId)
      .then(setDashboard)
      .catch(() => setInvalid(true));
  }, [api.getSharedDashboard, params.sessionId]);

  const selectedDashboard = useMemo<DirItem | null>(
    () => dashboard ? {
      id: `shared-${dashboard.id}`,
      data_id: String(dashboard.id),
      name: dashboard.name,
      desc: dashboard.desc ?? '',
      type: 'dashboard',
      is_build_in: dashboard.is_build_in,
    } : null,
    [dashboard],
  );

  const getDashboardDetail = useCallback(async () => dashboard, [dashboard]);
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

  if (invalid) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-bg-1)] p-8">
        <div className="w-full max-w-[400px] text-center">
          <h2 className="mb-2 text-base font-medium text-[var(--color-text-1)]">
            分享链接无效或已失效
          </h2>
          <p className="mb-6 text-sm leading-relaxed text-[var(--color-text-3)]">
            链接可能已被撤销、过期,或你没有访问权限。
          </p>
          <Button type="primary" onClick={() => router.push('/')}>
            返回首页
          </Button>
        </div>
      </div>
    );
  }
  if (!dashboard || !selectedDashboard) {
    return <Spin fullscreen tip="正在加载分享仪表盘" />;
  }

  return (
    <ShareDataSourceProvider value={shareAccess}>
      <OpsAnalysisProvider>
        <main className="h-full w-full overflow-hidden">
          <Dashboard
            selectedDashboard={selectedDashboard}
            shareMode
            shareSessionId={params.sessionId}
            getDashboardDetailOverride={getDashboardDetail}
          />
        </main>
      </OpsAnalysisProvider>
    </ShareDataSourceProvider>
  );
}
