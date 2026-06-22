import React, { useEffect, useMemo } from 'react';
import { Empty, Spin, Tooltip } from 'antd';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import { applyValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import {
  parsePoints,
  buildSegments,
} from './shared/stateTimelineData';

interface ComStateTimelineProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

// 默认状态调色板（无值映射时按出现顺序分配）
const FALLBACK_COLORS = [
  '#67a567',
  '#fd666d',
  '#EAB839',
  '#366ce4',
  '#9254de',
  '#36cfc9',
];

/**
 * State timeline / Status history（对齐 Grafana）：单行状态随时间的彩色分段。
 * 连续相同状态合并为一段，段宽按数据点数占比；颜色/文本经值映射，否则用默认调色板。
 */
const ComStateTimeline: React.FC<ComStateTimelineProps> = ({
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

  // 为无值映射的状态稳定分配调色板色
  const colorByState = useMemo(() => {
    const map = new Map<string | number, string>();
    let i = 0;
    for (const s of segments) {
      if (!map.has(s.v)) {
        map.set(s.v, FALLBACK_COLORS[i % FALLBACK_COLORS.length]);
        i += 1;
      }
    }
    return map;
  }, [segments]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }
  if (!hasData) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const total = points.length || 1;
  const resolve = (v: string | number) => {
    const m = applyValueMapping(v, config?.valueMappings);
    return {
      color: m?.color || colorByState.get(v) || '#bfbfbf',
      text: m?.text !== undefined ? m.text : String(v),
    };
  };

  return (
    <div className="flex h-full w-full flex-col justify-center gap-2 px-3">
      <div className="flex w-full overflow-hidden rounded" style={{ height: 28 }}>
        {segments.map((s, idx) => {
          const { color, text } = resolve(s.v);
          return (
            <Tooltip
              key={idx}
              title={`${text}｜${s.startT}${s.endT !== s.startT ? ` ~ ${s.endT}` : ''}`}
            >
              <div
                style={{
                  flexGrow: s.count / total,
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
      {/* 图例：去重状态 */}
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {[...new Set(segments.map((s) => s.v))].map((v) => {
          const { color, text } = resolve(v);
          return (
            <span key={String(v)} className="flex items-center gap-1 text-[11px]">
              <span
                className="inline-block rounded-sm"
                style={{ width: 10, height: 10, background: color }}
              />
              {text}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export default ComStateTimeline;
