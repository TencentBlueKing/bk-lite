'use client';

import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from 'react';
import { Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useReportApi } from '@/app/ops-analysis/api/report';
import type { ReportProps, ReportViewSets } from '@/app/ops-analysis/types/report';
import BasicCanvasPage from '../components/basicCanvasPage';

export interface ReportRef {
  hasUnsavedChanges: () => boolean;
}

const DEFAULT_VIEW_SETS: ReportViewSets = {
  time_range: null,
  sections: [],
};

const normalizeViewSets = (value: unknown): ReportViewSets => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return DEFAULT_VIEW_SETS;
  }

  const source = value as Partial<ReportViewSets>;
  return {
    time_range: source.time_range ?? null,
    sections: Array.isArray(source.sections) ? source.sections : [],
  };
};

const Report = forwardRef<ReportRef, ReportProps>(({ selectedReport }, ref) => {
  const { t } = useTranslation();
  const { getReportDetail } = useReportApi();
  const [loading, setLoading] = useState(false);
  const [viewSets, setViewSets] = useState<ReportViewSets>(DEFAULT_VIEW_SETS);

  useImperativeHandle(ref, () => ({
    hasUnsavedChanges: () => false,
  }));

  useEffect(() => {
    const reportId = selectedReport?.data_id;
    if (!reportId) {
      setViewSets(DEFAULT_VIEW_SETS);
      return;
    }

    let cancelled = false;
    setLoading(true);
    getReportDetail(reportId)
      .then((data) => {
        if (!cancelled) {
          setViewSets(normalizeViewSets(data?.view_sets));
        }
      })
      .catch((error) => {
        console.error('Failed to load report:', error);
        if (!cancelled) {
          setViewSets(DEFAULT_VIEW_SETS);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [getReportDetail, selectedReport?.data_id]);

  const stats = useMemo(
    () => [
      {
        label: t('opsAnalysis.report.sectionCount'),
        value: viewSets.sections.length,
      },
      {
        label: t('opsAnalysis.report.timeRange'),
        value: viewSets.time_range || '--',
      },
      {
        label: t('opsAnalysis.report.mode'),
        value: t('opsAnalysis.report.basicMode'),
      },
    ],
    [t, viewSets],
  );

  return (
    <BasicCanvasPage
      selectedItem={selectedReport}
      loading={loading}
      titleFallback={t('opsAnalysis.report.title')}
      emptyDescription={t('opsAnalysis.report.selectFirst')}
      stats={stats}
    >
      <div className="flex h-full min-h-[360px] items-center justify-center rounded-md border border-dashed border-[var(--color-border-2)] bg-[var(--color-bg-2)]">
        <Empty description={t('opsAnalysis.report.builderPending')} />
      </div>
    </BasicCanvasPage>
  );
});

Report.displayName = 'Report';

export default Report;
