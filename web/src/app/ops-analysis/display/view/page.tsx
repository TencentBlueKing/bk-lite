'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Spin } from 'antd';
import Screen from '@/app/ops-analysis/(pages)/view/screen';
import { useScreenDisplayApi } from '@/app/ops-analysis/api/screenDisplay';
import { ShareCanvasDetailProvider } from '@/app/ops-analysis/context/shareCanvasDetail';
import { ShareDataSourceProvider } from '@/app/ops-analysis/context/shareDataSource';
import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
import { ShareOrganizationProvider } from '@/app/ops-analysis/context/shareOrganization';
import { DashboardRenderOpsAnalysisProvider } from '@/app/ops-analysis/context/common';
import { useTranslation } from '@/utils/i18n';
import type { DirItem } from '@/app/ops-analysis/types';
import type { SharedCanvasDto } from '@/app/ops-analysis/types/dashboardShare';

export default function ScreenDisplayViewPage() {
  const { t } = useTranslation();
  const api = useScreenDisplayApi();
  const [canvas, setCanvas] = useState<SharedCanvasDto | null>(null);
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    api.getDisplayCanvas()
      .then((next: SharedCanvasDto) => {
        if (next?.resource_type !== 'screen') {
          setInvalid(true);
          return;
        }
        setCanvas(next);
      })
      .catch(() => setInvalid(true));
  }, [api.getDisplayCanvas]);

  const selectedItem = useMemo<DirItem | null>(
    () =>
      canvas
        ? {
          id: `display-screen-${canvas.id}`,
          data_id: String(canvas.id),
          name: canvas.name,
          desc: canvas.desc ?? '',
          type: 'screen',
          is_build_in: canvas.is_build_in,
        }
        : null,
    [canvas],
  );

  const getDetailOverride = useCallback(async () => canvas, [canvas]);
  const shareOrganization = useMemo(
    () => ({
      spaceId: canvas?.space_id,
      groupTree: Array.isArray(canvas?.group_tree) ? canvas.group_tree : [],
    }),
    [canvas],
  );
  const queryDataSource = useCallback(
    (dataSourceId: number, requestParams?: unknown) =>
      api.queryDisplayDataSource(dataSourceId, requestParams),
    [api.queryDisplayDataSource],
  );
  const shareAccess = useMemo(
    () => ({
      queryDataSource,
      getDataSourceDetails: () => api.getDisplayDataSources(),
    }),
    [api.getDisplayDataSources, queryDataSource],
  );

  if (invalid) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--color-bg-1)] p-8">
        <p className="m-0 max-w-[420px] text-center text-base text-[var(--color-text-1)]">
          {t('opsAnalysis.screen.displayInvalid')}
        </p>
      </div>
    );
  }

  if (!canvas || !selectedItem) {
    return <Spin fullscreen tip={t('opsAnalysis.screen.displayLoading')} />;
  }

  return (
    <ShareDataSourceProvider value={shareAccess}>
      <ShareCanvasDetailProvider value={getDetailOverride}>
        <ShareModeProvider value>
          <ShareOrganizationProvider value={shareOrganization}>
            <DashboardRenderOpsAnalysisProvider selectedGroupId={canvas.space_id}>
              <main className="h-full w-full overflow-hidden">
                <Screen selectedScreen={selectedItem} shareMode />
              </main>
            </DashboardRenderOpsAnalysisProvider>
          </ShareOrganizationProvider>
        </ShareModeProvider>
      </ShareCanvasDetailProvider>
    </ShareDataSourceProvider>
  );
}
