'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { DatePicker, Empty, Segmented, Skeleton, Tag } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import {
  DashboardExecutionStatusDistributionItem,
  DashboardJobTypeDistributionItem,
  DashboardStats,
  DashboardSuccessRateCompare,
  DashboardTrend,
  JobRecord,
  JobRecordSource,
  JobRecordStatus,
} from '@/app/job/types';

const { RangePicker } = DatePicker;

type OverviewDays = 7 | 30;
type OverviewRange = OverviewDays | 'custom';

// 自定义区间最大跨度（天，含首尾），需与后端 MAX_RANGE_DAYS 保持一致
const MAX_CUSTOM_RANGE_DAYS = 90;

interface OverviewData {
  trend: DashboardTrend[];
  successRateCompare: DashboardSuccessRateCompare | null;
  statusDist: DashboardExecutionStatusDistributionItem[];
}

const SUCCESS_COLOR = '#19b87a';
const FAILURE_COLOR = '#ff5a52';
const PRIMARY_COLOR = '#2d87ff';
const WARNING_COLOR = '#ff9c3c';
const PURPLE_COLOR = '#7c6cff';
const TEAL_COLOR = '#14b8a6';
const TRACK_COLOR = '#eef1f6';
const FALLBACK_COLOR = '#9aa7b8';

const STATUS_DIST_COLORS: Record<string, string> = {
  success: SUCCESS_COLOR,
  failed: FAILURE_COLOR,
  running: PRIMARY_COLOR,
  pending: WARNING_COLOR,
  timeout: '#f0883e',
  cancelling: '#faad14',
  cancelled: FALLBACK_COLOR,
};

// 固定展示的状态行（缺失补 0），保证状态卡行数恒定 → 右栏与趋势图高度稳定
const STATUS_DISPLAY: Array<{ key: string; labelKey: string }> = [
  { key: 'success', labelKey: 'job.statusSuccess' },
  { key: 'failed', labelKey: 'job.statusFailed' },
  { key: 'timeout', labelKey: 'job.statusTimeout' },
  { key: 'running', labelKey: 'job.statusRunning' },
  { key: 'pending', labelKey: 'job.statusPending' },
  { key: 'cancelled', labelKey: 'job.statusCanceled' },
];

const JOB_TYPE_COLORS: Record<string, string> = {
  script: PRIMARY_COLOR,
  file_distribution: TEAL_COLOR,
  playbook: PURPLE_COLOR,
};

const STATUS_COLOR_MAP: Record<JobRecordStatus, string> = {
  pending: '#faad14',
  running: '#1890ff',
  success: '#52c41a',
  failed: '#ff4d4f',
  timeout: '#ff4d4f',
  cancelled: '#8c8c8c',
  cancelling: '#faad14',
};

const formatPercent = (value: number | undefined) => `${(value || 0).toFixed(1)}%`;

const formatDuration = (seconds: number | undefined) => {
  const value = seconds || 0;
  if (value <= 0) return '0s';
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const secs = Math.round(value % 60);
  if (minutes < 60) return secs ? `${minutes}m ${secs}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins ? `${hours}h ${mins}m` : `${hours}h`;
};

const formatAxisDate = (date: string) => {
  const [year, month, day] = date.split('-');
  if (!year || !month || !day) return date;
  return `${month}-${day}`;
};

const getVisibleXAxisIndices = (length: number) => {
  if (length <= 7) return Array.from({ length }, (_, index) => index);

  const step = length <= 14 ? 2 : length <= 21 ? 3 : 5;
  const indices = new Set<number>([0, length - 1]);

  for (let index = 0; index < length; index += step) {
    indices.add(index);
  }

  return Array.from(indices).sort((a, b) => a - b);
};

const getChartPoint = (
  value: number,
  index: number,
  valuesLength: number,
  width: number,
  height: number,
  chartLeft: number,
  chartRight: number,
  chartTop: number,
  chartBottom: number,
  maxValue: number
) => {
  const drawableWidth = width - chartLeft - chartRight;
  const drawableHeight = height - chartTop - chartBottom;
  const x = valuesLength === 1 ? width / 2 : chartLeft + (index * drawableWidth) / (valuesLength - 1);
  const y = chartTop + drawableHeight - (maxValue === 0 ? 0 : (value / maxValue) * drawableHeight);

  return { x, y };
};

const buildLinePath = (
  values: number[],
  width: number,
  height: number,
  chartLeft: number,
  chartRight: number,
  chartTop: number,
  chartBottom: number,
  maxValue: number
) => {
  if (!values.length) return '';

  return values
    .map((value, index) => {
      const point = getChartPoint(value, index, values.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue);
      return `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`;
    })
    .join(' ');
};

const ChipIcon = ({ children }: { children: React.ReactNode }) => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    {children}
  </svg>
);

const ICON_EXEC = <path d="M4 17l6-6-6-6M12 19h8" />;
const ICON_CHECK = <path d="M20 6L9 17l-5-5" />;
const ICON_CLOCK = (
  <>
    <circle cx={12} cy={12} r={9} />
    <path d="M12 7v5l3 2" />
  </>
);
const ICON_CALENDAR = (
  <>
    <rect x={3} y={4} width={18} height={17} rx={2} />
    <path d="M16 2v4M8 2v4M3 10h18" />
  </>
);
const ICON_TIMER = (
  <>
    <circle cx={12} cy={13} r={8} />
    <path d="M12 13l3-2M9 2h6M12 5V2" />
  </>
);

const MiniHist = ({ values, color }: { values: number[]; color: string }) => {
  const max = Math.max(...values, 1);
  return (
    <div className="flex items-end gap-[2px] h-9 w-full">
      {values.map((value, index) => {
        const pct = value > 0 ? Math.max((value / max) * 100, 16) : 0;
        return (
          <div key={index} className="flex-1 h-full flex items-end rounded-[3px]" style={{ background: `${color}14` }}>
            <span className="block w-full rounded-[3px]" style={{ height: `${pct}%`, background: color }} />
          </div>
        );
      })}
    </div>
  );
};

const MiniProportion = ({ segments }: { segments: Array<{ value: number; color: string }> }) => {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0) || 1;
  return (
    <div className="flex w-full h-2 rounded-[5px] overflow-hidden" style={{ background: TRACK_COLOR }}>
      {segments.map((segment, index) => (
        <span key={index} style={{ width: `${(segment.value / total) * 100}%`, background: segment.color }} />
      ))}
    </div>
  );
};

const MiniProgress = ({ percent, color }: { percent: number; color: string }) => (
  <div className="w-full h-2 rounded-[5px] overflow-hidden" style={{ background: TRACK_COLOR }}>
    <span className="block h-full rounded-[5px]" style={{ width: `${percent}%`, background: color }} />
  </div>
);

const MiniSparkline = ({
  points,
  color,
  formatValue,
}: {
  points: Array<{ date: string; value: number }>;
  color: string;
  formatValue?: (value: number) => string;
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(120);
  const [hover, setHover] = useState<number | null>(null);
  const height = 40;
  const padX = 5;
  const padTop = 9;
  const padBottom = 6;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(Math.max(el.clientWidth, 40));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (points.length === 0) return <div ref={ref} className="w-full" style={{ height }} />;

  const max = Math.max(...points.map((p) => p.value), 1);
  const coords = points.map((p, index) => ({
    date: p.date,
    value: p.value,
    x: padX + (index * (width - padX * 2)) / Math.max(points.length - 1, 1),
    y: height - padBottom - (p.value / max) * (height - padTop - padBottom),
  }));
  const smooth = (pts: Array<{ x: number; y: number }>) => {
    if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`;
    let d = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 0; i < pts.length - 1; i += 1) {
      const p0 = pts[i - 1] || pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2] || p2;
      d += ` C ${p1.x + (p2.x - p0.x) / 6} ${p1.y + (p2.y - p0.y) / 6}, ${p2.x - (p3.x - p1.x) / 6} ${p2.y - (p3.y - p1.y) / 6}, ${p2.x} ${p2.y}`;
    }
    return d;
  };
  const line = smooth(coords);
  const area = `${line} L ${coords[coords.length - 1].x} ${height} L ${coords[0].x} ${height} Z`;
  const segW = (width - padX * 2) / Math.max(points.length, 1);
  const hovered = hover !== null ? coords[hover] : null;

  return (
    <div ref={ref} className="relative w-full" style={{ height }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
        <path d={area} fill={`${color}1f`} />
        <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {hovered && (
          <circle cx={hovered.x} cy={hovered.y} r={3} fill="#fff" stroke={color} strokeWidth="1.5" />
        )}
        {coords.map((c, index) => (
          <rect
            key={`hit-${index}`}
            x={c.x - segW / 2}
            y={0}
            width={segW}
            height={height}
            fill="transparent"
            onMouseEnter={() => setHover(index)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>
      {hovered && (
        <div
          className="absolute z-10 px-2 py-1 rounded-md text-[11px] text-white pointer-events-none whitespace-nowrap"
          style={{
            left: Math.min(Math.max(hovered.x, 30), width - 30),
            top: -4,
            transform: 'translate(-50%, -100%)',
            background: 'rgba(18, 26, 38, 0.92)',
          }}
        >
          {formatAxisDate(hovered.date)} · {formatValue ? formatValue(hovered.value) : hovered.value}
        </div>
      )}
    </div>
  );
};

const JobTypeDonut = ({ data, totalLabel }: { data: DashboardJobTypeDistributionItem[]; totalLabel: string }) => {
  const cx = 74;
  const cy = 74;
  const r = 54;
  const strokeWidth = 20;
  const circumference = 2 * Math.PI * r;
  const total = data.reduce((sum, item) => sum + item.count, 0);
  let accumulated = 0;

  return (
    <svg width="148" height="148" viewBox="0 0 148 148" className="shrink-0">
      {total > 0 ? (
        data.map((item, index) => {
          const fraction = item.count / total;
          const color = JOB_TYPE_COLORS[item.job_type] || FALLBACK_COLOR;
          const dashArray = `${fraction * circumference} ${circumference - fraction * circumference}`;
          const dashOffset = -accumulated * circumference;
          accumulated += fraction;
          return (
            <circle
              key={index}
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={color}
              strokeWidth={strokeWidth}
              strokeDasharray={dashArray}
              strokeDashoffset={dashOffset}
              transform={`rotate(-90 ${cx} ${cy})`}
            />
          );
        })
      ) : (
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={TRACK_COLOR} strokeWidth={strokeWidth} />
      )}
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize="11" fill="#90a0b3">
        {totalLabel}
      </text>
      <text x={cx} y={cy + 17} textAnchor="middle" fontSize="24" fontWeight="700" fill="#1f2a37">
        {total}
      </text>
    </svg>
  );
};

const TrendMiniChart = ({ data, t }: { data: DashboardTrend[]; t: (key: string) => string }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 960, height: 300 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setSize({ width: Math.max(el.clientWidth, 80), height: Math.max(el.clientHeight, 80) });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const width = size.width;
  const height = size.height;
  const chartLeft = 18;
  const chartRight = 18;
  const chartTop = 24;
  const chartBottom = 34;
  const yAxisValues = [0, 1, 2, 3];
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const maxValue = Math.max(...data.flatMap((item) => [item.execution_count, item.success_count, item.failed_count, item.cancelled_count]), 0);
  const visibleXAxisIndices = getVisibleXAxisIndices(data.length);
  // 区间较长时逐点数值会相互重叠，仅保留圆点与 hover tooltip
  const showValueLabels = data.length <= 31;
  const hoveredData = hoveredIndex !== null ? data[hoveredIndex] : null;
  const hoveredSuccessPoint = hoveredData
    ? getChartPoint(hoveredData.success_count, hoveredIndex as number, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue)
    : null;
  const hoveredFailurePoint = hoveredData
    ? getChartPoint(hoveredData.failed_count, hoveredIndex as number, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue)
    : null;
  const hoveredCancelledPoint = hoveredData
    ? getChartPoint(hoveredData.cancelled_count, hoveredIndex as number, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue)
    : null;
  const hoveredX = hoveredSuccessPoint?.x;
  const tooltipWidth = 164;
  const tooltipHeight = 122;
  const tooltipX = hoveredX
    ? Math.max(chartLeft, Math.min(hoveredX - tooltipWidth / 2, width - chartRight - tooltipWidth))
    : 0;
  const tooltipY = 10;

  if (!data.length) {
    return (
      <div ref={containerRef} className="absolute inset-0 flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
      </div>
    );
  }

  return (
    <div ref={containerRef} className="absolute inset-0">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
        {yAxisValues.map((step) => {
          const y = chartTop + ((height - chartTop - chartBottom) / (yAxisValues.length - 1)) * step;
          return <line key={step} x1={chartLeft} y1={y} x2={width - chartRight} y2={y} stroke="#eef3f9" strokeDasharray="4 4" />;
        })}
        <path
          d={buildLinePath(data.map((item) => item.success_count), width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue)}
          fill="none"
          stroke={SUCCESS_COLOR}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={buildLinePath(data.map((item) => item.failed_count), width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue)}
          fill="none"
          stroke={FAILURE_COLOR}
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="9 7"
        />
        <path
          d={buildLinePath(data.map((item) => item.cancelled_count), width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue)}
          fill="none"
          stroke={FALLBACK_COLOR}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="2 6"
        />
        {hoveredData && hoveredX ? (
          <g pointerEvents="none">
            <line x1={hoveredX} y1={chartTop} x2={hoveredX} y2={height - chartBottom} stroke="#b8cde2" strokeDasharray="4 4" />
            {hoveredSuccessPoint ? <circle cx={hoveredSuccessPoint.x} cy={hoveredSuccessPoint.y} r="5" fill="#fff" stroke={SUCCESS_COLOR} strokeWidth="2" /> : null}
            {hoveredFailurePoint ? <circle cx={hoveredFailurePoint.x} cy={hoveredFailurePoint.y} r="5" fill="#fff" stroke={FAILURE_COLOR} strokeWidth="2" /> : null}
            {hoveredCancelledPoint ? <circle cx={hoveredCancelledPoint.x} cy={hoveredCancelledPoint.y} r="5" fill="#fff" stroke={FALLBACK_COLOR} strokeWidth="2" /> : null}
            <g>
              <rect x={tooltipX} y={tooltipY} width={tooltipWidth} height={tooltipHeight} rx="12" fill="rgba(18, 26, 38, 0.92)" />
              <text x={tooltipX + 14} y={tooltipY + 22} fontSize="12" fontWeight="600" fill="#ffffff">
                {formatAxisDate(hoveredData.date)}
              </text>
              {[
                { key: 'success', color: SUCCESS_COLOR, label: t('job.successCount'), value: hoveredData.success_count },
                { key: 'failed', color: FAILURE_COLOR, label: t('job.failedCount'), value: hoveredData.failed_count },
                { key: 'cancelled', color: FALLBACK_COLOR, label: t('job.statusCanceled'), value: hoveredData.cancelled_count },
                { key: 'execution', color: '#8fa6bf', label: t('job.executionCount'), value: hoveredData.execution_count },
              ].map((item, index) => (
                <g key={item.key}>
                  <circle cx={tooltipX + 18} cy={tooltipY + 40 + index * 20} r="4" fill={item.color} />
                  <text x={tooltipX + 30} y={tooltipY + 44 + index * 20} fontSize="11" fill="#dce7f2">
                    {item.label}: {item.value}
                  </text>
                </g>
              ))}
            </g>
          </g>
        ) : null}
        {data.map((item, index) => {
          const currentPoint = getChartPoint(item.success_count, index, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue);
          const previousPoint =
            index > 0 ? getChartPoint(data[index - 1].success_count, index - 1, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue) : null;
          const nextPoint =
            index < data.length - 1 ? getChartPoint(data[index + 1].success_count, index + 1, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue) : null;
          const leftBound = previousPoint ? (previousPoint.x + currentPoint.x) / 2 : chartLeft;
          const rightBound = nextPoint ? (currentPoint.x + nextPoint.x) / 2 : width - chartRight;

          return (
            <rect
              key={item.date}
              x={leftBound}
              y={chartTop}
              width={Math.max(18, rightBound - leftBound)}
              height={height - chartTop - chartBottom}
              fill="transparent"
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            />
          );
        })}
        {data.map((item, index) => {
          const successPoint = getChartPoint(item.success_count, index, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue);
          const failurePoint = getChartPoint(item.failed_count, index, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue);
          const cancelledPoint = getChartPoint(item.cancelled_count, index, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue);

          return (
            <g key={`point-${item.date}`} pointerEvents="none">
              {showValueLabels && (
                <text x={successPoint.x} y={successPoint.y - 10} textAnchor="middle" fontSize="8" fontWeight="700" fill={SUCCESS_COLOR}>
                  {item.success_count}
                </text>
              )}
              <circle cx={successPoint.x} cy={successPoint.y} r="4" fill="#fff" stroke={SUCCESS_COLOR} strokeWidth="2" />
              <circle cx={failurePoint.x} cy={failurePoint.y} r="4" fill="#fff" stroke={FAILURE_COLOR} strokeWidth="2" />
              <circle cx={cancelledPoint.x} cy={cancelledPoint.y} r="4" fill="#fff" stroke={FALLBACK_COLOR} strokeWidth="2" />
            </g>
          );
        })}
        {data.map((item, index) => {
          if (!visibleXAxisIndices.includes(index)) {
            return null;
          }

          const { x } = getChartPoint(item.success_count, index, data.length, width, height, chartLeft, chartRight, chartTop, chartBottom, maxValue);

          return (
            <text
              key={item.date}
              x={x}
              y={height - 8}
              textAnchor={index === 0 ? 'start' : index === data.length - 1 ? 'end' : 'middle'}
              fontSize="11"
              fontWeight="500"
              fill="#8092a8"
            >
              {formatAxisDate(item.date)}
            </text>
          );
        })}
      </svg>
    </div>
  );
};

const getSourceConfig = (source: JobRecordSource | string | undefined) => {
  const configs: Record<string, { color: string; bg: string; border: string }> = {
    manual: { color: '#2d87ff', bg: 'rgba(45, 135, 255, 0.08)', border: '#2d87ff' },
    scheduled: { color: '#ff6600', bg: 'rgba(255, 102, 0, 0.08)', border: '#ff6600' },
    api: { color: '#722ed1', bg: 'rgba(114, 46, 209, 0.08)', border: '#722ed1' },
  };
  return configs[source || 'manual'] || configs.manual;
};

const JobHomePage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { isLoading } = useApiClient();
  const {
    getDashboardSuccessRateCompare,
    getDashboardTrend,
    getDashboardStats,
    getDashboardJobTypeDistribution,
    getDashboardExecutionStatusDistribution,
    getJobRecordList,
  } = useJobApi();

  const [recentJobs, setRecentJobs] = useState<JobRecord[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [period, setPeriod] = useState<OverviewRange>(7);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [typeDist, setTypeDist] = useState<DashboardJobTypeDistributionItem[]>([]);
  const [overviewDataMap, setOverviewDataMap] = useState<Record<OverviewDays, OverviewData>>({
    7: { trend: [], successRateCompare: null, statusDist: [] },
    30: { trend: [], successRateCompare: null, statusDist: [] },
  });
  // 自定义区间：按需拉取，独立于 7/30 的预取数据
  const [customRange, setCustomRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [pickingDates, setPickingDates] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [customData, setCustomData] = useState<OverviewData>({ trend: [], successRateCompare: null, statusDist: [] });
  const [customLoading, setCustomLoading] = useState(false);

  const fetchRecentJobs = useCallback(async () => {
    setRecentLoading(true);
    try {
      const res = await getJobRecordList({ page: 1, page_size: 8 });
      setRecentJobs(res.items || res.results || []);
    } catch {
      setRecentJobs([]);
    } finally {
      setRecentLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchOverviewData = useCallback(async () => {
    setOverviewLoading(true);
    try {
      const [trend7, compare7, status7, trend30, compare30, status30, statsRes, typeRes] = await Promise.all([
        getDashboardTrend({ days: 7 }),
        getDashboardSuccessRateCompare({ days: 7 }),
        getDashboardExecutionStatusDistribution({ days: 7 }),
        getDashboardTrend({ days: 30 }),
        getDashboardSuccessRateCompare({ days: 30 }),
        getDashboardExecutionStatusDistribution({ days: 30 }),
        getDashboardStats(),
        getDashboardJobTypeDistribution(),
      ]);

      setOverviewDataMap({
        7: { trend: trend7 || [], successRateCompare: compare7 || null, statusDist: status7 || [] },
        30: { trend: trend30 || [], successRateCompare: compare30 || null, statusDist: status30 || [] },
      });
      setStats(statsRes || null);
      setTypeDist(typeRes || []);
    } catch {
      setOverviewDataMap({
        7: { trend: [], successRateCompare: null, statusDist: [] },
        30: { trend: [], successRateCompare: null, statusDist: [] },
      });
      setStats(null);
      setTypeDist([]);
    } finally {
      setOverviewLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isLoading) {
      fetchRecentJobs();
      fetchOverviewData();
    }
  }, [isLoading, fetchOverviewData, fetchRecentJobs]);

  // 选定完整的自定义区间后按需拉取（7/30 仍走预取，切换即时生效）
  useEffect(() => {
    if (!customRange || !customRange[0] || !customRange[1]) return;

    let cancelled = false;
    const startDate = customRange[0].format('YYYY-MM-DD');
    const endDate = customRange[1].format('YYYY-MM-DD');

    const fetchCustomData = async () => {
      setCustomLoading(true);
      try {
        const [trend, compare, statusRes] = await Promise.all([
          getDashboardTrend({ startDate, endDate }),
          getDashboardSuccessRateCompare({ startDate, endDate }),
          getDashboardExecutionStatusDistribution({ startDate, endDate }),
        ]);
        if (!cancelled) {
          setCustomData({ trend: trend || [], successRateCompare: compare || null, statusDist: statusRes || [] });
        }
      } catch {
        if (!cancelled) {
          setCustomData({ trend: [], successRateCompare: null, statusDist: [] });
        }
      } finally {
        if (!cancelled) setCustomLoading(false);
      }
    };

    fetchCustomData();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customRange]);

  const selectedOverviewData = period === 'custom' ? customData : overviewDataMap[period];
  const currentPeriod = selectedOverviewData.successRateCompare?.current_period;
  const trendData = selectedOverviewData.trend || [];
  const statusDist = selectedOverviewData.statusDist || [];
  const analyticsLoading = overviewLoading || (period === 'custom' && customLoading);

  const executionTotal = currentPeriod?.execution_total ?? 0;
  const successCount = currentPeriod?.success_count ?? 0;
  const failedCount = currentPeriod?.failed_count ?? 0;
  const successRate = currentPeriod?.success_rate ?? 0;
  const successRateIncrease = selectedOverviewData.successRateCompare?.success_rate_increase ?? 0;
  const deltaUp = successRateIncrease >= 0;
  const periodLabel =
    period === 'custom'
      ? customRange?.[0] && customRange?.[1]
        ? `${customRange[0].format('YYYY-MM-DD')} ~ ${customRange[1].format('YYYY-MM-DD')}`
        : t('job.selectDateRange')
      : period === 7
        ? t('job.last7Days')
        : t('job.last30Days');

  // 自定义区间：禁选未来日期，并限制最大跨度 MAX_CUSTOM_RANGE_DAYS 天
  const disabledOverviewDate = useCallback(
    (current: Dayjs) => {
      if (!current) return false;
      if (current.isAfter(dayjs().endOf('day'))) return true;
      const from = pickingDates?.[0];
      const to = pickingDates?.[1];
      if (from && current.diff(from, 'day') >= MAX_CUSTOM_RANGE_DAYS) return true;
      if (to && to.diff(current, 'day') >= MAX_CUSTOM_RANGE_DAYS) return true;
      return false;
    },
    [pickingDates]
  );

  const runningCount = stats?.execution_running ?? 0;
  const pendingCount = stats?.execution_pending ?? 0;

  const cronEnabled = stats?.scheduled_task_enabled ?? 0;
  const cronTotal = stats?.scheduled_task_total ?? 0;
  const cronRate = cronTotal ? Math.round((cronEnabled / cronTotal) * 100) : 0;
  const avgDurationSeconds = currentPeriod?.avg_duration_seconds ?? 0;

  const statusCountMap = statusDist.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = item.count;
    return acc;
  }, {});
  const statusTotal = statusDist.reduce((sum, item) => sum + item.count, 0);
  const typeTotal = typeDist.reduce((sum, item) => sum + item.count, 0);

  const healthGood = executionTotal === 0 || successRate >= 90;

  const formatTime = (timeStr: string | null | undefined) => {
    if (!timeStr) return '-';
    const d = new Date(timeStr);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const getStatusText = (status: JobRecordStatus) => {
    const statusTextMap: Record<JobRecordStatus, string> = {
      pending: t('job.statusPending'),
      running: t('job.statusRunning'),
      success: t('job.statusSuccess'),
      failed: t('job.statusFailed'),
      timeout: t('job.statusTimeout'),
      cancelled: t('job.statusCanceled'),
      cancelling: t('job.statusCancelling'),
    };
    return statusTextMap[status] || status;
  };

  const getSourceText = (source: JobRecordSource | undefined) => {
    if (!source) return '-';
    const sourceTextMap: Record<JobRecordSource, string> = {
      manual: t('job.manual'),
      scheduled: t('job.scheduled'),
      api: 'API',
    };
    return sourceTextMap[source] || source;
  };

  const handleViewDetail = (record: JobRecord) => {
    router.push(`/job/execution/job-record?id=${record.id}`);
  };

  const recentJobColumns = [
    { title: t('job.jobName'), dataIndex: 'name', key: 'name', width: 200 },
    {
      title: t('job.jobType'),
      dataIndex: 'job_type_display',
      key: 'job_type_display',
      width: 120,
      render: (text: string) => (
        <Tag style={{ color: 'var(--color-text-3)', backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border-1)', margin: 0 }}>{text}</Tag>
      ),
    },
    {
      title: t('job.triggerSource'),
      dataIndex: 'trigger_source',
      key: 'trigger_source',
      width: 120,
      render: (_: unknown, record: JobRecord) => {
        const source = record.trigger_source || record.source;
        const display = record.trigger_source_display || record.source_display;
        const style = getSourceConfig(source);
        return (
          <Tag style={{ color: style.color, backgroundColor: style.bg, borderColor: style.border, margin: 0 }}>
            {display || getSourceText(source as JobRecordSource)}
          </Tag>
        );
      },
    },
    {
      title: t('job.executionStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (_: unknown, record: JobRecord) => {
        const color = STATUS_COLOR_MAP[record.status] || '#8c8c8c';
        return (
          <Tag style={{ color, backgroundColor: `${color}10`, borderColor: color, margin: 0 }}>
            {record.status_display || getStatusText(record.status)}
          </Tag>
        );
      },
    },
    {
      title: t('job.startTime'),
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      render: (_: unknown, record: JobRecord) => formatTime(record.started_at),
    },
    {
      title: t('job.executor'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 120,
      render: (text: string) => text || '-',
    },
    {
      title: t('job.operation'),
      key: 'action',
      width: 100,
      render: (_: unknown, record: JobRecord) => (
        <a className="text-(--color-primary) cursor-pointer" onClick={() => handleViewDetail(record)}>
          {t('job.viewDetail')}
        </a>
      ),
    },
  ];

  const cardClass = 'bg-(--color-bg) rounded-xl border border-(--color-border-1) shadow-sm';

  return (
    <div className="w-full">
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4 mb-4">
        {/* 执行次数 */}
        <div className={`${cardClass} p-4 flex flex-col`}>
          <div className="flex items-center gap-2 mb-3.5">
            <span className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0" style={{ background: 'rgba(45,135,255,.10)', color: PRIMARY_COLOR }}>
              <ChipIcon>{ICON_EXEC}</ChipIcon>
            </span>
            <span className="text-[13px] text-(--color-text-2) font-medium">{t('job.executionCount')}</span>
            <span className="ml-auto text-[11px] text-(--color-text-3) px-2 py-0.5 rounded-md" style={{ background: TRACK_COLOR }}>{periodLabel}</span>
          </div>
          <div className="flex items-baseline gap-2.5">
            <span className="text-[30px] font-bold leading-none tracking-tight text-(--color-text-1)">{executionTotal}</span>
          </div>
          <div className="mt-2 text-xs text-(--color-text-3)">{t('job.success')} {successCount} · {t('job.failed')} {failedCount}</div>
          <div className="mt-auto pt-4"><MiniHist values={trendData.map((item) => item.execution_count)} color={PRIMARY_COLOR} /></div>
        </div>

        {/* 成功率 */}
        <div className={`${cardClass} p-4 flex flex-col`}>
          <div className="flex items-center gap-2 mb-3.5">
            <span className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0" style={{ background: 'rgba(25,184,122,.12)', color: SUCCESS_COLOR }}>
              <ChipIcon>{ICON_CHECK}</ChipIcon>
            </span>
            <span className="text-[13px] text-(--color-text-2) font-medium">{t('job.successRate')}</span>
            <span className="ml-auto text-[11px] text-(--color-text-3) px-2 py-0.5 rounded-md" style={{ background: TRACK_COLOR }}>{periodLabel}</span>
          </div>
          <div className="flex items-baseline gap-2.5">
            <span className="text-[30px] font-bold leading-none tracking-tight" style={{ color: SUCCESS_COLOR }}>{formatPercent(successRate)}</span>
            <span className="text-xs font-semibold" style={{ color: deltaUp ? '#0e8a59' : '#d83f37' }}>
              {deltaUp ? '▲' : '▼'} {Math.abs(successRateIncrease).toFixed(1)}%
            </span>
          </div>
          <div className="mt-2 text-xs text-(--color-text-3)">{t('job.successRateChange')}</div>
          <div className="mt-auto pt-4"><MiniSparkline points={trendData.map((item) => ({ date: item.date, value: item.success_count }))} color={SUCCESS_COLOR} /></div>
        </div>

        {/* 运行中 */}
        <div className={`${cardClass} p-4 flex flex-col`}>
          <div className="flex items-center gap-2 mb-3.5">
            <span className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0" style={{ background: 'rgba(255,156,60,.14)', color: WARNING_COLOR }}>
              <ChipIcon>{ICON_CLOCK}</ChipIcon>
            </span>
            <span className="text-[13px] text-(--color-text-2) font-medium">{t('job.kpiRunning')}</span>
          </div>
          <div className="flex items-baseline gap-2.5">
            <span className="text-[30px] font-bold leading-none tracking-tight" style={{ color: WARNING_COLOR }}>{runningCount}</span>
          </div>
          <div className="mt-2 text-xs text-(--color-text-3)">{t('job.kpiPending')} {pendingCount} · {t('job.kpiQueued')} 0</div>
          <div className="mt-auto pt-4"><MiniProportion segments={[{ value: runningCount, color: WARNING_COLOR }, { value: pendingCount, color: '#ffd6a8' }]} /></div>
        </div>

        {/* 定时任务 */}
        <div className={`${cardClass} p-4 flex flex-col`}>
          <div className="flex items-center gap-2 mb-3.5">
            <span className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0" style={{ background: 'rgba(124,108,255,.12)', color: PURPLE_COLOR }}>
              <ChipIcon>{ICON_CALENDAR}</ChipIcon>
            </span>
            <span className="text-[13px] text-(--color-text-2) font-medium">{t('job.scheduledTask')}</span>
          </div>
          <div className="flex items-baseline gap-2.5">
            <span className="text-[30px] font-bold leading-none tracking-tight text-(--color-text-1)">
              {cronEnabled}
              <small className="text-sm font-semibold text-(--color-text-3) ml-1">/ {cronTotal}</small>
            </span>
          </div>
          <div className="mt-2 text-xs text-(--color-text-3)">{t('job.enabledRate')} {cronRate}%</div>
          <div className="mt-auto pt-4"><MiniProgress percent={cronRate} color={PURPLE_COLOR} /></div>
        </div>

        {/* 平均执行时长 */}
        <div className={`${cardClass} p-4 flex flex-col`}>
          <div className="flex items-center gap-2 mb-3.5">
            <span className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0" style={{ background: 'rgba(20,184,166,.12)', color: TEAL_COLOR }}>
              <ChipIcon>{ICON_TIMER}</ChipIcon>
            </span>
            <span className="text-[13px] text-(--color-text-2) font-medium">{t('job.avgDuration')}</span>
          </div>
          <div className="flex items-baseline gap-2.5">
            <span className="text-[30px] font-bold leading-none tracking-tight text-(--color-text-1)">{formatDuration(avgDurationSeconds)}</span>
          </div>
          <div className="mt-2 text-xs text-(--color-text-3)">{t('job.avgDurationSub')}</div>
          <div className="mt-auto pt-4"><MiniSparkline points={trendData.map((item) => ({ date: item.date, value: item.avg_duration_seconds }))} color={TEAL_COLOR} formatValue={formatDuration} /></div>
        </div>
      </div>

      {/* Analytics grid */}
      <div className="grid grid-cols-1 xl:grid-cols-[1.9fr_1fr] gap-4 mb-4 items-stretch">
        {/* 执行趋势 */}
        <div className={`${cardClass} flex flex-col`}>
          <div className="flex items-center justify-between px-5 pt-4 gap-3 flex-wrap">
            <div className="flex items-center gap-4">
              <h3 className="text-[15px] font-semibold text-(--color-text-1)">{t('job.executionTrend')}</h3>
              <div className="flex items-center gap-3.5 text-xs text-(--color-text-2)">
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: SUCCESS_COLOR }} />{t('job.success')}</span>
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: FAILURE_COLOR }} />{t('job.failed')}</span>
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: FALLBACK_COLOR }} />{t('job.statusCanceled')}</span>
              </div>
            </div>
            <div className="flex items-center gap-2.5 flex-wrap">
              {period === 'custom' && (
                <RangePicker
                  size="small"
                  value={customRange}
                  allowClear={false}
                  disabledDate={disabledOverviewDate}
                  onCalendarChange={(dates) => setPickingDates(dates as [Dayjs | null, Dayjs | null] | null)}
                  onChange={(value) => {
                    if (value && value[0] && value[1]) {
                      setCustomRange([value[0], value[1]]);
                    }
                  }}
                />
              )}
              <Segmented<OverviewRange>
                size="small"
                value={period}
                onChange={(value) => setPeriod(value)}
                options={[
                  { label: t('job.last7Days'), value: 7 },
                  { label: t('job.last30Days'), value: 30 },
                  { label: t('job.customRange'), value: 'custom' },
                ]}
              />
            </div>
          </div>
          <div className="flex-1 min-h-0 relative">
            {analyticsLoading ? (
              <div className="absolute inset-4"><Skeleton active paragraph={{ rows: 5 }} /></div>
            ) : (
              <TrendMiniChart data={trendData} t={t} />
            )}
          </div>
        </div>

        {/* 右栏：状态分布 + 类型分布 */}
        <div className="flex flex-col gap-4">
          <div className={cardClass}>
            <div className="flex items-center justify-between px-5 pt-4">
              <h3 className="text-[15px] font-semibold text-(--color-text-1)">{t('job.executionStatusDistribution')}</h3>
              {!analyticsLoading && (
                <span
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md"
                  style={healthGood ? { color: '#0e8a59', background: 'rgba(25,184,122,.12)' } : { color: '#b9700e', background: 'rgba(255,156,60,.16)' }}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: healthGood ? SUCCESS_COLOR : WARNING_COLOR }} />
                  {healthGood ? t('job.overallHealthGood') : t('job.overallHealthWarn')}
                </span>
              )}
            </div>
            <div className="px-5 py-4 flex flex-col gap-3">
              {analyticsLoading ? (
                <Skeleton active paragraph={{ rows: 5 }} title={false} />
              ) : (
                STATUS_DISPLAY.map(({ key, labelKey }) => {
                  const count = statusCountMap[key] ?? 0;
                  const color = STATUS_DIST_COLORS[key] || FALLBACK_COLOR;
                  const pct = statusTotal ? Math.round((count / statusTotal) * 100) : 0;
                  const barPct = Math.min(100, statusTotal ? Math.max((count / statusTotal) * 100, count > 0 ? 4 : 0) : 0);
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <span className="flex items-center gap-2 w-20 shrink-0 text-[13px] text-(--color-text-2)">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                        <span className="truncate">{t(labelKey)}</span>
                      </span>
                      <span className="w-8 text-right text-[13px] font-semibold text-(--color-text-1) tabular-nums shrink-0">{count}</span>
                      <span className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: TRACK_COLOR }}>
                        <span className="block h-full rounded-full" style={{ maxWidth: '100%', width: `${barPct}%`, background: color }} />
                      </span>
                      <span className="w-9 text-right text-[11px] text-(--color-text-3) tabular-nums shrink-0">{pct}%</span>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className={cardClass}>
            <div className="px-5 pt-4">
              <h3 className="text-[15px] font-semibold text-(--color-text-1)">{t('job.jobTypeDistribution')}</h3>
            </div>
            <div className="px-5 py-4 flex items-center gap-5">
              {overviewLoading ? (
                <Skeleton active paragraph={{ rows: 3 }} />
              ) : (
                <>
                  <JobTypeDonut data={typeDist} totalLabel={t('job.totalLabel')} />
                  <div className="flex-1 flex flex-col gap-2.5">
                    {typeDist.length === 0 ? (
                      <span className="text-(--color-text-3) text-sm">{t('common.noData')}</span>
                    ) : (
                      typeDist.map((item) => {
                        const color = JOB_TYPE_COLORS[item.job_type] || FALLBACK_COLOR;
                        return (
                          <div key={item.job_type} className="flex items-center justify-between text-[13px]">
                            <span className="flex items-center gap-2 text-(--color-text-2)">
                              <span className="w-2.5 h-2.5 rounded-[3px]" style={{ background: color }} />
                              {item.job_type_display}
                            </span>
                            <span className="font-semibold text-(--color-text-1)">
                              {item.count}
                              <span className="text-(--color-text-3) font-normal text-xs ml-1">{typeTotal ? Math.round((item.count / typeTotal) * 100) : 0}%</span>
                            </span>
                          </div>
                        );
                      })
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Recent jobs */}
      <div className={`${cardClass} p-5`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[15px] font-semibold text-(--color-text-1)">{t('job.recentJobs')}</h3>
          <a className="text-sm text-(--color-primary) cursor-pointer" onClick={() => router.push('/job/execution/job-record')}>
            {t('job.viewAll')} →
          </a>
        </div>
        <CustomTable columns={recentJobColumns} dataSource={recentJobs} loading={recentLoading} rowKey="id" pagination={false} size="middle" />
      </div>
    </div>
  );
};

export default JobHomePage;
