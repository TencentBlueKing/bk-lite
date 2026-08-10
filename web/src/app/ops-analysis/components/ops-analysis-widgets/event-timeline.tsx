import React, { useEffect } from 'react';
import { Alert, Tag } from 'antd';
import ChartSurface from '@/components/chart-surface';
import type { ValueConfig } from '@/app/ops-analysis/components/ops-analysis-widgets';
import {
  DEFAULT_EVENT_TIMELINE_MAX_ITEMS,
  parseEventTimelineItems,
} from '@/app/ops-analysis/utils/eventTimeline';
import { useTranslation } from '@/utils/i18n';

export interface OpsAnalysisEventTimelineProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const STATUS_COLORS: Record<string, string> = {
  info: '#1677ff',
  warning: '#faad14',
  error: '#ff4d4f',
  success: '#52c41a',
  unknown: '#8c8c8c',
  neutral: '#bfbfbf',
};

const OpsAnalysisEventTimeline: React.FC<OpsAnalysisEventTimelineProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const { t } = useTranslation();
  const timelineConfig = config?.eventTimeline;
  const parsed = parseEventTimelineItems(rawData, {
    sortOrder: timelineConfig?.sortOrder,
    maxItems: DEFAULT_EVENT_TIMELINE_MAX_ITEMS,
  });
  const hasData = parsed.items.length > 0;

  useEffect(() => {
    if (!loading) {
      onReady?.(hasData);
    }
  }, [hasData, loading, onReady]);

  return (
    <ChartSurface
      loading={loading}
      hasData={hasData}
      containerClassName="flex h-full min-h-0 w-full flex-col p-3"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      {parsed.truncated ? (
        <Alert
          type="warning"
          showIcon
          className="mb-2"
          message={`${t('dashboard.eventTimelineOverflowWarning')} (${parsed.total}/${DEFAULT_EVENT_TIMELINE_MAX_ITEMS})`}
        />
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <div className="relative pl-5">
          {parsed.items.map((item, index) => (
            <div key={`${item.time}-${item.title}-${index}`} className="relative pb-4">
              <span
                className="absolute left-[-15px] top-1 h-2.5 w-2.5 rounded-full"
                style={{
                  backgroundColor: item.status
                    ? STATUS_COLORS[item.status]
                    : STATUS_COLORS.neutral,
                }}
              />
              {index !== parsed.items.length - 1 ? (
                <span className="absolute left-[-11px] top-4 h-[calc(100%-8px)] w-px bg-(--color-border-2)" />
              ) : null}
              <div className="flex items-center gap-2 text-xs text-(--color-text-3)">
                <span>{item.time}</span>
                {item.category ? <Tag bordered={false}>{item.category}</Tag> : null}
              </div>
              <div className="mt-1 text-sm font-medium text-(--color-text-1)">
                {item.link ? (
                  <a href={item.link} target="_blank" rel="noopener noreferrer">
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
              </div>
              {item.description ? (
                <div className="mt-1 whitespace-pre-wrap text-xs text-(--color-text-2)">
                  {item.description}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </ChartSurface>
  );
};

export default OpsAnalysisEventTimeline;
