'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, message, Segmented, Tooltip } from 'antd';
import {
  CopyOutlined,
  CheckOutlined,
  ReloadOutlined,
  LineChartOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  FilterValue,
  UnifiedFilterDefinition,
  WidgetConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
const WidgetDataRenderer = React.lazy(
  () => import('@/app/ops-analysis/components/widgetDataRenderer'),
);
import { WidgetHeaderRuntimeSlotProvider } from '@/app/ops-analysis/components/widgetHeaderRuntimeSlot';

export type WidgetConfigPreviewTab = 'chart' | 'json';

const PREVIEW_CHART_HEIGHT = 320;
const PREVIEW_SINGLE_HEIGHT = 168;

interface WidgetConfigPreviewProps {
  widgetId: string;
  previewed: boolean;
  stale: boolean;
  config: WidgetConfig | null;
  dataSource?: DatasourceItem;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterDefinitions?: UnifiedFilterDefinition[];
  builtinNamespaceId?: number;
  surface?: OpsAnalysisWidgetSurface;
  reloadVersion: number;
  rawData: unknown;
  onRawData: (data: unknown) => void;
  liveName?: string;
  liveDescription?: string;
  onRefresh?: () => void;
}

const formatRawJson = (data: unknown): string => {
  if (data === null || data === undefined) {
    return '';
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
};

const WidgetConfigPreview: React.FC<WidgetConfigPreviewProps> = ({
  widgetId,
  previewed,
  stale,
  config,
  dataSource,
  unifiedFilterValues,
  filterDefinitions,
  builtinNamespaceId,
  surface = 'dashboard',
  reloadVersion,
  rawData,
  onRawData,
  liveName,
  liveDescription,
  onRefresh,
}) => {
  const { t } = useTranslation();
  const [tab, setTab] = useState<WidgetConfigPreviewTab>('chart');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!previewed) {
      setTab('chart');
    }
  }, [previewed]);

  const handleTabChange = useCallback((value: string | number) => {
    setTab(value === 'json' ? 'json' : 'chart');
  }, []);

  const jsonText = useMemo(() => formatRawJson(rawData), [rawData]);
  const title = liveName || config?.name || t('dashboard.configPreviewUntitled');
  const description = liveDescription ?? config?.description;
  const previewChartHeight =
    config?.chartType === 'single' ? PREVIEW_SINGLE_HEIGHT : PREVIEW_CHART_HEIGHT;

  const handleCopyJson = useCallback(async () => {
    if (!jsonText) return;
    try {
      await navigator.clipboard.writeText(jsonText);
      setCopied(true);
      message.success(t('common.copySuccess'));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      message.error(t('common.copyFailed'));
    }
  }, [jsonText, t]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3" data-testid="widget-config-preview">
      <div className="flex h-8 shrink-0 items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1">
          <span className="truncate text-[13px] font-semibold leading-none text-(--color-text-1)">
            {t('dashboard.configPreview')}
          </span>
          {previewed && onRefresh ? (
            stale ? (
              <Button
                type="text"
                size="small"
                className="inline-flex !h-7 !w-7 shrink-0 items-center justify-center text-(--ant-color-warning) hover:text-(--ant-color-warning)"
                icon={<ReloadOutlined aria-hidden />}
                aria-label={t('dashboard.configPreviewRefresh')}
                onClick={onRefresh}
                data-testid="widget-config-preview-refresh"
              />
            ) : (
              <Tooltip title={t('dashboard.configPreviewRefresh')}>
                <Button
                  type="text"
                  size="small"
                  className="inline-flex !h-7 !w-7 shrink-0 items-center justify-center text-(--color-text-3) hover:text-(--color-primary)"
                  icon={<ReloadOutlined aria-hidden />}
                  aria-label={t('dashboard.configPreviewRefresh')}
                  onClick={onRefresh}
                  data-testid="widget-config-preview-refresh"
                />
              </Tooltip>
            )
          ) : null}
          {previewed && stale ? (
            <span
              data-testid="widget-config-preview-stale"
              className="relative inline-flex h-5 shrink-0 items-center rounded-sm border border-(--ant-color-warning-border) bg-(--ant-color-warning-bg) px-2 text-[11px] font-medium leading-none text-(--ant-color-warning)"
            >
              <span
                aria-hidden
                className="absolute top-1/2 -left-[5px] -mt-[5px] border-y-[5px] border-r-[5px] border-y-transparent border-r-(--ant-color-warning-border)"
              />
              <span
                aria-hidden
                className="absolute top-1/2 -left-[4px] -mt-[4px] border-y-[4px] border-r-[4px] border-y-transparent border-r-(--ant-color-warning-bg)"
              />
              {t('dashboard.configPreviewStale')}
            </span>
          ) : null}
        </div>

        {previewed ? (
          <Segmented
            size="small"
            value={tab}
            onChange={handleTabChange}
            options={[
              {
                label: (
                  <span className="inline-flex h-full items-center gap-1 text-xs leading-none">
                    <LineChartOutlined />
                    {t('dashboard.configPreviewChart')}
                  </span>
                ),
                value: 'chart',
              },
              {
                label: (
                  <span className="inline-flex h-full items-center gap-1 text-xs leading-none">
                    <CodeOutlined />
                    {t('dashboard.configPreviewRawJson')}
                  </span>
                ),
                value: 'json',
              },
            ]}
          />
        ) : null}
      </div>

      {!previewed ? (
        <div
          className="flex min-h-[200px] items-center justify-center rounded-lg bg-(--color-fill-1) px-6 py-10 text-center"
          data-testid="widget-config-preview-empty"
        >
          <p className="text-sm text-(--color-text-2)">{t('dashboard.configPreviewEmpty')}</p>
        </div>
      ) : (
        <div className="flex shrink-0 flex-col overflow-hidden rounded-lg bg-(--color-fill-1)/40">
          <div className="shrink-0 px-4 py-3">
            <h4 className="truncate text-sm font-medium leading-5 text-(--color-text-1)">
              {title}
            </h4>
            {description?.trim() ? (
              <p className="mt-1 line-clamp-2 text-xs leading-normal text-(--color-text-3)">
                {description}
              </p>
            ) : null}
          </div>

          <div className="px-3 pb-3">
            {tab === 'json' ? (
              <div className="relative overflow-hidden rounded-md bg-(--color-bg)">
                {jsonText ? (
                  <Button
                    type="text"
                    size="small"
                    icon={copied ? <CheckOutlined className="text-(--color-success)" /> : <CopyOutlined />}
                    onClick={handleCopyJson}
                    data-testid="widget-config-preview-copy-json"
                    className="absolute right-1 top-1 z-10 !h-6 !px-2 text-xs text-(--color-text-3)"
                  >
                    {copied
                      ? t('common.copySuccess')
                      : t('common.copy')}
                  </Button>
                ) : null}
                <pre
                  className="max-h-[500px] min-h-[300px] overflow-auto p-3 pr-16 text-xs font-mono leading-relaxed text-(--color-text-1) scrollbar-thin"
                  data-testid="widget-config-preview-json"
                >
                  {jsonText || t('dashboard.configPreviewRawJsonEmpty')}
                </pre>
              </div>
            ) : null}

            <div
              className={tab === 'chart' ? 'w-full overflow-hidden' : 'hidden'}
              style={tab === 'chart' ? { height: previewChartHeight } : undefined}
              data-testid="widget-config-preview-chart"
            >
              <WidgetHeaderRuntimeSlotProvider>
                {(runtimeSlotRef) => (
                  <div className="flex h-full min-h-0 w-full flex-col">
                    <div
                      ref={runtimeSlotRef}
                      className="mb-1 max-w-full shrink-0 overflow-x-auto"
                    />
                    {config ? (
                      <div className="h-full min-h-0 flex-1">
                        <React.Suspense fallback={null}>
                          <WidgetDataRenderer
                            widgetId={widgetId}
                            chartType={config.chartType}
                            config={config}
                            dataSource={dataSource}
                            unifiedFilterValues={unifiedFilterValues}
                            filterDefinitions={filterDefinitions}
                            builtinNamespaceId={builtinNamespaceId}
                            surface={surface}
                            reloadVersion={String(reloadVersion)}
                            runtimeActive
                            onRawData={onRawData}
                          />
                        </React.Suspense>
                      </div>
                    ) : null}
                  </div>
                )}
              </WidgetHeaderRuntimeSlotProvider>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WidgetConfigPreview;
