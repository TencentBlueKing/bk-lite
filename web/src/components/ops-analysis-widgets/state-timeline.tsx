import React, { useEffect, useMemo } from 'react';
import { Tooltip } from 'antd';
import { applyValueMapping } from '@/components/ops-analysis-config-sections';
import type { ValueConfig } from '@/components/ops-analysis-widgets';
import ChartSurface from '@/components/chart-surface';
import { buildSegments, parsePoints } from '@/components/ops-analysis-widgets/state-timeline-data';

export interface OpsAnalysisStateTimelineProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const FALLBACK_COLORS = [
  '#67a567',
  '#fd666d',
  '#EAB839',
  '#366ce4',
  '#9254de',
  '#36cfc9',
];

const OpsAnalysisStateTimeline: React.FC<OpsAnalysisStateTimelineProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const points = useMemo(() => parsePoints(rawData), [rawData]);
  const segments = useMemo(() => buildSegments(points), [points]);
  const hasData = segments.length > 0;

  useEffect(() => {
    if (!loading) onReady?.(hasData);
  }, [hasData, loading, onReady]);

  const colorByState = useMemo(() => {
    const nextMap = new Map<string | number, string>();
    let index = 0;
    for (const segment of segments) {
      if (!nextMap.has(segment.v)) {
        nextMap.set(segment.v, FALLBACK_COLORS[index % FALLBACK_COLORS.length]);
        index += 1;
      }
    }
    return nextMap;
  }, [segments]);

  const total = points.length || 1;
  const resolveState = (value: string | number) => {
    const mapping = applyValueMapping(value, config?.valueMappings);
    return {
      color: mapping?.color || colorByState.get(value) || '#bfbfbf',
      text: mapping?.text !== undefined ? mapping.text : String(value),
    };
  };

  return (
    <ChartSurface
      loading={loading}
      hasData={hasData}
      containerClassName="flex h-full w-full flex-col justify-center gap-2 px-3"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      <div className="flex w-full overflow-hidden rounded" style={{ height: 28 }}>
        {segments.map((segment, index) => {
          const { color, text } = resolveState(segment.v);
          return (
            <Tooltip
              key={index}
              title={`${text}｜${segment.startT}${segment.endT !== segment.startT ? ` ~ ${segment.endT}` : ''}`}
            >
              <div
                style={{
                  flexGrow: segment.count / total,
                  flexBasis: 0,
                  background: color,
                  minWidth: 2,
                }}
              />
            </Tooltip>
          );
        })}
      </div>
      <div className="flex justify-between text-[10px] text-(--color-text-4)">
        <span>{points[0]?.t}</span>
        <span>{points[points.length - 1]?.t}</span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {[...new Set(segments.map((segment) => segment.v))].map((value) => {
          const { color, text } = resolveState(value);
          return (
            <span key={String(value)} className="flex items-center gap-1 text-[11px]">
              <span
                className="inline-block rounded-sm"
                style={{ width: 10, height: 10, background: color }}
              />
              {text}
            </span>
          );
        })}
      </div>
    </ChartSurface>
  );
};

export default OpsAnalysisStateTimeline;
