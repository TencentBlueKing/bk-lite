'use client';

import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Button, Select, Spin, Tooltip } from 'antd';
import {
  ArrowLeftOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  FallOutlined,
  InfoCircleOutlined,
  NodeIndexOutlined,
  RiseOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import { Area, AreaChart, ResponsiveContainer } from 'recharts';
import TimeSelector from '@/components/time-selector';
import LineChart from '@/app/monitor/components/charts/lineChart';
import useViewApi from '@/app/monitor/api/view';
import MetricViews from '@/app/monitor/components/metric-views';
import useMonitorApi from '@/app/monitor/api';
import { useTranslation } from '@/utils/i18n';
import { ListItem } from '@/types';
import {
  calculateMetrics,
  getRecentTimeRange,
  mergeViewQueryKeyValues,
  renderChart
} from '@/app/monitor/utils/common';
import { ChartData, MetricItem, TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import { SearchParams } from '@/app/monitor/types/search';
import {
  DASHBOARD_METRICS,
  MONGODB_COLLECTION_STATUS_QUERY,
  TREND_LEGENDS
} from './config';
import { MetricSeries, MetricUnit, MongoMetricConfig } from './types';
import styles from './index.module.scss';

interface InstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
}

interface GuideItem {
  label: string;
  detail: string;
}

const MAX_POINTS = 100;
const DEFAULT_STEP = 360;
const MEBIBYTE = 1024 * 1024;
const MONGODB_REFRESH_FREQUENCY_LIST: ListItem[] = [
  { label: '关闭', value: 0 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '2m', value: 120000 },
  { label: '5m', value: 300000 },
  { label: '10m', value: 600000 }
];
const COLLECTION_STATUS_SEGMENT_COUNT = 18;
const COLLECTION_STATUS_LEGEND = [
  { key: 'success' as const, label: '正常', color: '#22c55e' },
  { key: 'empty' as const, label: '无数据', color: '#cbd5e1' },
  { key: 'error' as const, label: '异常', color: '#ff4d4f' }
];

const formatBinary = (value: number) => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let next = value;
  let idx = 0;
  while (Math.abs(next) >= 1024 && idx < units.length - 1) {
    next /= 1024;
    idx += 1;
  }
  return {
    value: next >= 100 ? next.toFixed(0) : next.toFixed(1),
    unit: units[idx]
  };
};

const formatBinaryPerSecond = (value: number) => {
  const formatted = formatBinary(value);
  return {
    ...formatted,
    unit: formatted.unit ? `${formatted.unit}/s` : ''
  };
};

const formatRuntimeNs = (value: number) => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  const seconds = value / 1e9;
  if (seconds < 60) {
    return { value: seconds.toFixed(0), unit: 's' };
  }

  if (seconds < 3600) {
    return { value: (seconds / 60).toFixed(seconds >= 600 ? 0 : 1), unit: 'min' };
  }

  if (seconds < 86400) {
    return { value: (seconds / 3600).toFixed(seconds >= 36000 ? 0 : 1), unit: 'h' };
  }

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return { value: `${days}d ${hours}h`, unit: '' };
};

const getChartPointSeriesTotal = (point?: ChartData) =>
  Object.entries(point || {}).reduce((sum, [key, value]) => {
    if (!key.startsWith('value') || typeof value !== 'number' || !Number.isFinite(value)) {
      return sum;
    }
    return sum + value;
  }, 0);

const countRestartsInRange = (data: ChartData[] = []) => {
  const points = [...data]
    .map((point) => ({
      time: Number(point.time),
      value: getChartPointSeriesTotal(point)
    }))
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value) && point.value >= 0)
    .sort((a, b) => a.time - b.time);

  if (points.length < 2) {
    return 0;
  }

  let restartCount = 0;

  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const drop = previous.value - current.value;
    const gapSeconds = Math.max((current.time - previous.time) / 1000, 0);
    const tolerance = Math.max(30, gapSeconds * 0.2);

    if (drop > tolerance && current.value < previous.value * 0.98) {
      restartCount += 1;
    }
  }

  return restartCount;
};

const formatLatencyNs = (value: number) => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  if (value < 1e3) {
    return { value: value.toFixed(0), unit: 'ns' };
  }

  if (value < 1e6) {
    return { value: (value / 1e3).toFixed(value >= 1e5 ? 0 : 1), unit: 'us' };
  }

  if (value < 1e9) {
    return { value: (value / 1e6).toFixed(value >= 1e8 ? 0 : 1), unit: 'ms' };
  }

  return { value: (value / 1e9).toFixed(2), unit: 's' };
};

const formatMetricValue = (value: number, unit: MetricUnit) => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  switch (unit) {
    case 'ns':
      return formatLatencyNs(value);
    case 'percent':
      return { value: value.toFixed(1), unit: '%' };
    case 'cps':
      return { value: value >= 100 ? value.toFixed(0) : value.toFixed(1), unit: '/s' };
    case 'byteps':
      return formatBinaryPerSecond(value);
    case 'bytes':
      return formatBinary(value);
    case 'mebibytes':
      return formatBinary(value * MEBIBYTE);
    case 'counts':
      return { value: value.toFixed(0), unit: '' };
    case 'none':
      return { value: value.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1'), unit: '' };
    default:
      return { value: value.toFixed(1), unit: '' };
  }
};

const resolveDisplayUnit = (maxValue: number, suffix = '') => {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let divisor = 1;
  let unitIndex = 0;
  while (maxValue / divisor >= 1024 && unitIndex < units.length - 1) {
    divisor *= 1024;
    unitIndex += 1;
  }
  return {
    divisor,
    label: `${units[unitIndex]}${suffix}`
  };
};

const scaleChartDataValues = (data: ChartData[], divisor: number) => {
  if (!Number.isFinite(divisor) || divisor <= 0 || divisor === 1) {
    return data;
  }

  return data.map((point) => {
    const next: ChartData = { ...point };
    Object.entries(point).forEach(([key, current]) => {
      if (key.startsWith('value') && typeof current === 'number' && Number.isFinite(current)) {
        next[key] = current / divisor;
      }
    });
    return next;
  });
};

const multiplyChartDataValues = (data: ChartData[], factor: number) =>
  data.map((point) => {
    const next: ChartData = { ...point };
    Object.entries(point).forEach(([key, current]) => {
      if (key.startsWith('value') && typeof current === 'number' && Number.isFinite(current)) {
        next[key] = current * factor;
      }
    });
    return next;
  });

const normalizeDisplayText = (value?: string | null) => {
  if (!value) {
    return '';
  }
  const trimmed = value.trim();
  if (!trimmed || trimmed === '--') {
    return '';
  }
  const withoutQuotes = trimmed.replace(/^["'`\[(,\s]+|["'`,;\])\s]+$/g, '').trim();
  if (!withoutQuotes || withoutQuotes === '--') {
    return '';
  }
  if (
    /^[A-Za-z0-9+/=_-]{12,}$/.test(withoutQuotes) &&
    !/[.:/]/.test(withoutQuotes) &&
    !/[a-z]+-[a-z]/.test(withoutQuotes)
  ) {
    return '';
  }
  return withoutQuotes;
};

const buildInstanceDisplayName = (item: any) => {
  const primaryName = normalizeDisplayText(item.instance_name) || normalizeDisplayText(item.name);
  const hostPort = normalizeDisplayText(item.host && item.port ? `${item.host}:${item.port}` : '');
  const endpoint = normalizeDisplayText(item.endpoint) || normalizeDisplayText(item.url);
  const fallbackHost = normalizeDisplayText(item.host) || normalizeDisplayText(item.ip);

  if (primaryName && hostPort && !primaryName.includes(hostPort)) {
    return `${primaryName} (${hostPort})`;
  }
  if (primaryName) {
    return primaryName;
  }
  return hostPort || endpoint || fallbackHost || normalizeDisplayText(item.instance_id) || '--';
};

const buildInstanceSearchTokens = (item: any, displayName: string) =>
  Array.from(
    new Set(
      [
        displayName,
        normalizeDisplayText(item.instance_name),
        normalizeDisplayText(item.name),
        normalizeDisplayText(item.host),
        normalizeDisplayText(item.ip),
        normalizeDisplayText(item.port),
        normalizeDisplayText(item.endpoint),
        normalizeDisplayText(item.url),
        normalizeDisplayText(item.instance_id)
      ].filter(Boolean)
    )
  );

const parseLegacyParamList = (value?: string | null) => {
  if (!value) {
    return [] as string[];
  }
  return Array.from(
    new Set(
      value
        .replace(/[()\[\]'"`]/g, '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );
};

const getCollectionStatusTones = (metric?: MetricSeries | null) => {
  if (!Array.isArray(metric?.viewData)) {
    return [] as Array<'success' | 'empty'>;
  }
  return [...metric.viewData]
    .sort((a, b) => Number(a.time) - Number(b.time))
    .slice(-COLLECTION_STATUS_SEGMENT_COUNT)
    .map((point) => (Number(point.value1 ?? 0) > 0 ? ('success' as const) : ('empty' as const)));
};

const buildCollectionStatusTimeline = (metric?: MetricSeries | null) => {
  if (metric?.loadState === 'error') {
    return Array.from({ length: COLLECTION_STATUS_SEGMENT_COUNT }, () => 'error' as const);
  }
  const tones = getCollectionStatusTones(metric);
  if (tones.length >= COLLECTION_STATUS_SEGMENT_COUNT) {
    return tones;
  }
  return [
    ...Array.from({ length: COLLECTION_STATUS_SEGMENT_COUNT - tones.length }, () => 'empty' as const),
    ...tones
  ];
};

const buildSearchParams = (
  query: string,
  source_unit: string,
  idValues: string[],
  instanceIdKeys: string[],
  timeValues: TimeValuesProps
): SearchParams => {
  const effectiveIdValues = idValues.length ? idValues : [''];
  const labels = mergeViewQueryKeyValues([
    { keys: instanceIdKeys.length ? instanceIdKeys : ['instance_id'], values: effectiveIdValues }
  ]);
  const recentTimeRange = getRecentTimeRange(timeValues);
  const startTime = recentTimeRange.at(0);
  const endTime = recentTimeRange.at(1);
  const params: SearchParams = {
    query: query.replace(/__\$labels__/g, labels),
    source_unit,
    auto_convert_unit: false
  };

  if (startTime && endTime) {
    params.start = startTime;
    params.end = endTime;
    params.step = Math.max(
      Math.ceil((params.end / MAX_POINTS - params.start / MAX_POINTS) / DEFAULT_STEP),
      1
    );
  }

  return params;
};

const getLatestChartValue = (data: ChartData[]) => {
  const latestValue = calculateMetrics(data as Record<string, number>[]).latestValue;
  return typeof latestValue === 'number' ? latestValue : 0;
};

const buildPreviousPeriodTimeValues = (timeValues: TimeValuesProps): TimeValuesProps | null => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);
  if (!startTime || !endTime) {
    return null;
  }
  const duration = endTime - startTime;
  return {
    timeRange: [startTime - duration, endTime - duration],
    originValue: 0
  };
};

const getPeriodCompare = (currentValue: number, previousValue: number) => {
  if (!Number.isFinite(currentValue) || !Number.isFinite(previousValue)) {
    return null;
  }
  if (previousValue === 0) {
    if (currentValue === 0) {
      return { direction: 'flat' as const, value: '0.0%' };
    }
    return { direction: 'up' as const, value: '100%' };
  }
  const delta = ((currentValue - previousValue) / Math.abs(previousValue)) * 100;
  if (Math.abs(delta) < 0.05) {
    return { direction: 'flat' as const, value: '0.0%' };
  }
  return {
    direction: delta > 0 ? ('up' as const) : ('down' as const),
    value: `${Math.abs(delta).toFixed(1)}%`
  };
};

const getCompareTone = (direction: 'up' | 'down' | 'flat') => {
  if (direction === 'flat') {
    return 'flat';
  }
  return direction === 'up' ? 'positive' : 'negative';
};

const toMetricSeries = (
  metric: MongoMetricConfig,
  result: any,
  instanceId: React.Key,
  instanceName: string,
  idValues: string[],
  instanceIdKeys: string[]
): MetricSeries => {
  const viewData = renderChart(result?.data?.result || [], [
    {
      instance_id_values: idValues,
      instance_name: instanceName,
      instance_id: String(instanceId || ''),
      instance_id_keys: instanceIdKeys,
      dimensions: metric.dimensions || [],
      title: metric.display_name
    }
  ]);

  return {
    ...metric,
    viewData,
    loadState: 'success'
  };
};

const buildMetricItem = (metric: MetricSeries): MetricItem => ({
  id: 0,
  metric_group: 0,
  metric_object: 0,
  name: metric.name,
  type: 'number',
  display_name: metric.display_name,
  dimensions: metric.dimensions || [],
  unit: metric.unit,
  query: metric.query,
  description: metric.description,
  color: metric.color,
  viewData: metric.viewData
});

const mergeChartSeries = (
  seriesList: Array<{ key: string; label: string; displayName?: string; data: ChartData[] }>
): ChartData[] => {
  const merged = new Map<number, ChartData>();
  seriesList.forEach((series, index) => {
    const valueKey = `value${index + 1}`;
    series.data.forEach((point) => {
      const time = Number(point.time);
      const current = merged.get(time) || {
        time,
        title: series.label,
        details: {}
      };
      current[valueKey] = Number(point.value1 ?? 0);
      current.details = current.details || {};
      current.details[valueKey] = [
        {
          name: series.key,
          label: series.displayName || '',
          value: series.displayName || series.label
        }
      ];
      merged.set(time, current);
    });
  });
  return Array.from(merged.values()).sort((a, b) => Number(a.time) - Number(b.time));
};

const MiniTrendChart = ({ data, color }: { data: ChartData[]; color: string }) => {
  const gradientId = useId().replace(/:/g, '_');
  const chartData = useMemo(
    () =>
      data
        .map((point) => ({
          time: Number(point.time),
          value: Number(point.value1 ?? 0)
        }))
        .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value)),
    [data]
  );

  if (!chartData.length) {
    return <div className={styles.miniTrendPlaceholder} />;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.24} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill={`url(#${gradientId})`} dot={false} activeDot={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
};

const GuideTooltipContent = ({ items }: { items: GuideItem[] }) => (
  <div className={styles.metricGuideTooltip}>
    {items.map((item) => (
      <div key={item.label} className={styles.metricGuideTooltipRow}>
        <strong>{item.label}</strong>
        <span>{item.detail}</span>
      </div>
    ))}
  </div>
);

const TitleWithGuide = ({ title, items, className }: { title: React.ReactNode; items: GuideItem[]; className?: string }) => (
  <span className={[styles.titleWithGuide, className].filter(Boolean).join(' ')}>
    <span>{title}</span>
    <Tooltip overlayClassName="lightMetricTooltip" title={<GuideTooltipContent items={items} />}>
      <InfoCircleOutlined className={styles.metricGuideIcon} />
    </Tooltip>
  </span>
);

const StatCard = ({
  title,
  value,
  unit,
  icon,
  iconStyle,
  color,
  footer,
  compare,
  trendData = [],
  hideTrend = false,
  noDataType = 'empty',
  className,
  bodyClassName,
  extra
}: {
  title: React.ReactNode;
  value: React.ReactNode;
  unit: string;
  icon: React.ReactNode;
  iconStyle: React.CSSProperties;
  color: string;
  footer: React.ReactNode;
  compare?: { direction: 'up' | 'down' | 'flat'; value: string } | null;
  trendData?: ChartData[];
  hideTrend?: boolean;
  noDataType?: 'empty' | 'error';
  className?: string;
  bodyClassName?: string;
  extra?: React.ReactNode;
}) => {
  const compareTone = compare ? getCompareTone(compare.direction) : 'flat';
  return (
    <div className={`${styles.statCard} ${className || ''}`}>
      <div className={styles.statHeader}>
        <div className={styles.statLabel}>{title}</div>
        <div className={styles.statIcon} style={iconStyle}>{icon}</div>
      </div>
      <div className={`${styles.statBody} ${bodyClassName || ''}`}>
        <div className={styles.statValue} style={{ color }}>
          {value}
          {unit ? <span className={styles.statUnit}>{unit}</span> : null}
        </div>
        {compare ? (
          <div className={`${styles.statCompare} ${styles[`statCompare${compareTone === 'flat' ? 'Flat' : compareTone === 'positive' ? 'Positive' : 'Negative'}`]}`}>
            <span className={styles.statCompareLabel}>较上一周期</span>
            <span className={styles.statCompareValue}>
              {compare.direction === 'up' ? <RiseOutlined /> : compare.direction === 'down' ? <FallOutlined /> : null}
              {compare.value}
            </span>
          </div>
        ) : null}
        <div className={styles.statMeta}>{footer}</div>
      </div>
      {extra ? <div className={styles.statExtra}>{extra}</div> : null}
      {!hideTrend ? (
        <div className={styles.miniTrend}>
          <MiniTrendChart data={noDataType === 'error' ? [] : trendData} color={color} />
        </div>
      ) : null}
    </div>
  );
};

const CollectionStatusCard = ({
  status,
  timeline
}: {
  status: ReturnType<typeof getCollectionStatus>;
  timeline: Array<'success' | 'empty' | 'error'>;
}) => (
  <div className={`${styles.statCard} ${styles.collectionStatusCard}`}>
    <div className={styles.collectionStatusHeader}>
      <div className={styles.statLabel}>
        <TitleWithGuide
          title="采集状态"
          items={[
            { label: '采集状态', detail: '展示最近一段时间内该实例监控采集是否正常、缺失或异常。' },
            { label: '状态时间线', detail: '绿色表示采集成功，灰色表示暂无数据，红色表示采集或查询异常。' }
          ]}
          className={styles.statTitleWithGuide}
        />
      </div>
    </div>
    <div className={styles.collectionStatusBody}>
      <div
        className={`${styles.collectionStatusValue} ${
          styles[`collectionStatusValue${status.label === '正常' ? 'Success' : status.label === '异常' ? 'Error' : 'Empty'}`]
        }`}
      >
        {status.label}
      </div>
      <div className={styles.collectionStatusTimelineBlock}>
        <div className={styles.collectionStatusTimelineTitle}>状态时间线</div>
        <div className={styles.collectionStatusTimeline}>
          {timeline.map((tone, index) => (
            <span
              key={`${tone}-${index}`}
              className={`${styles.collectionStatusSegment} ${
                styles[`collectionStatusSegment${tone === 'success' ? 'Success' : tone === 'error' ? 'Error' : 'Empty'}`]
              }`}
            />
          ))}
        </div>
        <div className={styles.collectionStatusLegend}>
          {COLLECTION_STATUS_LEGEND.map((item) => (
            <span key={item.key} className={styles.collectionStatusLegendItem}>
              <span className={styles.collectionStatusLegendDot} style={{ background: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  </div>
);

const getCollectionStatus = (metric?: MetricSeries | null) => {
  const hasError = metric?.loadState === 'error';
  if (hasError) {
    return {
      label: '异常',
      tagColor: 'error' as const,
      detail: '当前采集状态指标查询失败，请检查探针与 MongoDB 实例连通性或采集配置。'
    };
  }
  const latestTone = getCollectionStatusTones(metric).at(-1);
  if (latestTone === 'success') {
    return {
      label: '正常',
      tagColor: 'success' as const,
      detail: '当前采集状态指标可正常返回，说明 MongoDB 监控采集链路正常。'
    };
  }
  return {
    label: '无数据',
    tagColor: 'warning' as const,
    detail: '当前时间范围内尚未看到 MongoDB 采集数据，请检查时间范围或等待新数据进入。'
  };
};

export default function MongoDashboardPage() {
  const { getInstanceQuery } = useViewApi();
  const { getInstanceList } = useMonitorApi();
  useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayMode, setDisplayMode] = useState<'dashboard' | 'metrics'>('dashboard');
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({ timeRange: [], originValue: 15 });
  const [timeDefaultValue, setTimeDefaultValue] = useState<TimeSelectorDefaultValue>({
    selectValue: 15,
    rangePickerVaule: null
  });
  const [frequence, setFrequence] = useState<number>(0);
  const [series, setSeries] = useState<Record<string, MetricSeries>>({});
  const [previousSeries, setPreviousSeries] = useState<Record<string, MetricSeries>>({});
  const [collectionStatusMetric, setCollectionStatusMetric] = useState<MetricSeries | null>(null);
  const [instanceOptions, setInstanceOptions] = useState<InstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [metricsRefreshSignal, setMetricsRefreshSignal] = useState(0);

  const monitorObjectId = searchParams.get('monitorObjId') || '';
  const monitorObjectName = searchParams.get('name') || 'Mongodb';
  const monitorObjDisplayName = searchParams.get('monitorObjDisplayName') || 'MongoDB';
  const rawInstanceId = searchParams.get('instance_id') || '';
  const parsedLegacyInstanceIds = parseLegacyParamList(rawInstanceId);
  const instanceId: React.Key = parsedLegacyInstanceIds[0] || rawInstanceId || '';
  const instanceName = searchParams.get('instance_name') || '--';
  const idValues = (() => {
    const explicitValues = parseLegacyParamList(searchParams.get('instance_id_values'));
    if (explicitValues.length > 0) return explicitValues;
    if (parsedLegacyInstanceIds.length > 0) return parsedLegacyInstanceIds;
    const normalizedInstanceId = normalizeDisplayText(String(instanceId));
    return normalizedInstanceId ? [normalizedInstanceId] : [];
  })();
  const instanceIdKeys = (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean);
  const objectDisplayText = normalizeDisplayText(monitorObjDisplayName) || normalizeDisplayText(monitorObjectName) || 'MongoDB';
  const normalizedInstanceName = normalizeDisplayText(instanceName);
  const isDashboardMode = displayMode === 'dashboard';

  useEffect(() => {
    if (!monitorObjectId) {
      setInstanceOptions([]);
      return;
    }
    let active = true;
    const loadInstances = async () => {
      try {
        setInstanceLoading(true);
        const data = await getInstanceList(monitorObjectId, { page_size: -1 });
        if (!active) return;
        const uniqueOptions = new Map<string, InstanceOption>();
        (data?.results || []).forEach((item: any) => {
          const value = String(item.instance_id || '');
          if (!value || uniqueOptions.has(value)) return;
          const label = buildInstanceDisplayName(item);
          uniqueOptions.set(value, {
            label,
            value,
            instanceIdValues:
              Array.isArray(item.instance_id_values) && item.instance_id_values.length ? item.instance_id_values : [value],
            searchTokens: buildInstanceSearchTokens(item, label)
          });
        });
        setInstanceOptions(Array.from(uniqueOptions.values()));
      } catch {
        if (active) setInstanceOptions([]);
      } finally {
        if (active) setInstanceLoading(false);
      }
    };
    loadInstances();
    return () => {
      active = false;
    };
  }, [monitorObjectId]);

  const idValuesKey = JSON.stringify(idValues);
  const currentInstanceCandidates = instanceOptions.filter(
    (item) => item.value === String(instanceId || '') || item.instanceIdValues.some((value) => idValues.includes(value))
  );
  const currentInstanceOption =
    currentInstanceCandidates.find((item) => normalizedInstanceName && item.label === normalizedInstanceName) ||
    currentInstanceCandidates[0];
  const resolvedInstanceName = currentInstanceOption?.label || normalizedInstanceName || '--';
  const hasReadableInstanceName = Boolean(normalizedInstanceName && normalizedInstanceName !== String(instanceId || ''));
  const instanceSelectOptions = useMemo(() => {
    const options = [...instanceOptions];
    const selectedValue = String(instanceId || '');
    if (selectedValue && hasReadableInstanceName && !options.some((item) => item.value === selectedValue)) {
      options.unshift({
        value: selectedValue,
        label: normalizedInstanceName,
        instanceIdValues: idValues.length ? idValues : [selectedValue],
        searchTokens: [normalizedInstanceName]
      });
    }
    return options;
  }, [hasReadableInstanceName, idValuesKey, instanceId, instanceOptions, normalizedInstanceName]);
  const instanceSelectValue =
    currentInstanceOption?.value || (hasReadableInstanceName && instanceId ? String(instanceId) : undefined);

  const loadMetrics = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      if (isDashboardMode) {
        const previousTimeValues = buildPreviousPeriodTimeValues(timeValues);
        const compareMetrics = DASHBOARD_METRICS.filter((metric) =>
          ['mongodb_connections_current', 'mongodb_commands_rate', 'mongodb_wtcache_usage_ratio'].includes(metric.name)
        );

        const metricResultsPromise = Promise.all(
          DASHBOARD_METRICS.map((metric) =>
            getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, timeValues))
              .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
              .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
          )
        );

        const collectionStatusPromise: Promise<MetricSeries> = getInstanceQuery(
          buildSearchParams(MONGODB_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, timeValues)
        )
          .then((result) =>
            toMetricSeries(
              {
                name: 'mongodb_collection_status',
                display_name: '采集状态',
                description: 'MongoDB 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts',
                query: MONGODB_COLLECTION_STATUS_QUERY,
                color: '#27c274'
              },
              result,
              instanceId,
              resolvedInstanceName,
              idValues,
              instanceIdKeys
            )
          )
          .catch(
            () =>
              ({
                name: 'mongodb_collection_status',
                display_name: '采集状态',
                description: 'MongoDB 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts' as MetricUnit,
                query: MONGODB_COLLECTION_STATUS_QUERY,
                color: '#27c274',
                viewData: [],
                loadState: 'error' as const
              }) satisfies MetricSeries
          );

        const previousMetricResultsPromise = previousTimeValues
          ? Promise.all(
            compareMetrics.map((metric) =>
              getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, previousTimeValues))
                .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
                .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
            )
          )
          : Promise.resolve([] as Array<readonly [string, MetricSeries]>);

        const [results, previousResults, collectionStatus] = await Promise.all([
          metricResultsPromise,
          previousMetricResultsPromise,
          collectionStatusPromise
        ]);

        setSeries(Object.fromEntries(results));
        setPreviousSeries(Object.fromEntries(previousResults));
        setCollectionStatusMetric(collectionStatus);
      } else {
        setSeries({});
        setPreviousSeries({});
        setCollectionStatusMetric(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isDashboardMode) {
      loadMetrics();
      return;
    }
    setLoading(false);
  }, [instanceId, idValuesKey, timeValues, isDashboardMode]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (frequence > 0 && isDashboardMode) {
      timerRef.current = setInterval(() => {
        loadMetrics(true);
      }, frequence);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [frequence, timeValues, instanceId, idValuesKey, isDashboardMode]);

  const metricMap = useMemo(() => series, [series]);
  const previousMetricMap = useMemo(() => previousSeries, [previousSeries]);
  const getLatest = (name: string) => getLatestChartValue(metricMap[name]?.viewData || []);
  const hasMetricData = (name: string) => {
    const target = metricMap[name];
    return target?.loadState === 'success' && Array.isArray(target.viewData) && target.viewData.length > 0;
  };
  const renderMetricValue = (name: string, value: string) => (hasMetricData(name) ? value : '--');

  const uptimeValue = getLatest('mongodb_uptime_ns');
  const currentConnections = getLatest('mongodb_connections_current');
  const availableConnections = getLatest('mongodb_connections_available');
  const openConnections = getLatest('mongodb_open_connections');
  const commandsRate = getLatest('mongodb_commands_rate');
  const queriesRate = getLatest('mongodb_queries_rate');
  const writesRate = getLatest('mongodb_write_ops_rate');
  const readLatency = getLatest('mongodb_latency_reads_avg');
  const commandLatency = getLatest('mongodb_latency_commands_avg');
  const pageFaults = getLatest('mongodb_page_faults_rate');
  const queuedReads = getLatest('mongodb_queued_reads');
  const queuedWrites = getLatest('mongodb_queued_writes');
  const residentMemory = getLatest('mongodb_resident_megabytes');
  const virtualMemory = getLatest('mongodb_vsize_megabytes');
  const allocatedMemory = getLatest('mongodb_tcmalloc_current_allocated_bytes');
  const cacheCurrent = getLatest('mongodb_wtcache_current_bytes');
  const cacheMax = getLatest('mongodb_wtcache_max_bytes_configured');
  const cacheDirty = getLatest('mongodb_wtcache_tracked_dirty_bytes');
  const cacheUsageRatio = getLatest('mongodb_wtcache_usage_ratio');
  const cacheDirtyRatio = getLatest('mongodb_wtcache_dirty_ratio');
  const netIn = getLatest('mongodb_net_in_bytes_count_rate');
  const netOut = getLatest('mongodb_net_out_bytes_count_rate');
  const cursorTimedOut = getLatest('mongodb_cursor_timed_out_count');
  const userAssert = getLatest('mongodb_assert_user');

  const collectionStatus = getCollectionStatus(collectionStatusMetric);
  const collectionStatusTimeline = buildCollectionStatusTimeline(collectionStatusMetric);
  const metricEmptyText = collectionStatus.label === '异常' ? '查询失败' : '暂无采集数据';

  const uptimeDisplay = formatRuntimeNs(uptimeValue);
  const connectionsDisplay = formatMetricValue(currentConnections, 'counts');
  const commandsDisplay = formatMetricValue(commandsRate, 'cps');
  const queriesDisplay = formatMetricValue(queriesRate, 'cps');
  const writesDisplay = formatMetricValue(writesRate, 'cps');
  const readLatencyDisplay = formatLatencyNs(readLatency);
  const commandLatencyDisplay = formatLatencyNs(commandLatency);
  const pageFaultDisplay = formatMetricValue(pageFaults, 'cps');
  const cacheUsageDisplay = formatMetricValue(cacheUsageRatio, 'percent');
  const cacheDirtyRatioDisplay = formatMetricValue(cacheDirtyRatio, 'percent');
  const cacheCurrentDisplay = formatBinary(cacheCurrent);
  const cacheMaxDisplay = formatBinary(cacheMax);
  const cacheDirtyDisplay = formatBinary(cacheDirty);
  const residentDisplay = formatMetricValue(residentMemory, 'mebibytes');
  const virtualDisplay = formatMetricValue(virtualMemory, 'mebibytes');
  const allocatedDisplay = formatMetricValue(allocatedMemory, 'bytes');
  const netInDisplay = formatBinaryPerSecond(netIn);
  const netOutDisplay = formatBinaryPerSecond(netOut);

  const startupTimeDisplay =
    Number.isFinite(uptimeValue) && uptimeValue >= 0
      ? dayjs().subtract(Math.floor(uptimeValue / 1e9), 'second').format('YYYY-MM-DD HH:mm:ss')
      : metricEmptyText;
  const uptimeRestarts = countRestartsInRange(metricMap.mongodb_uptime_ns?.viewData || []);
  const uptimeState = !hasMetricData('mongodb_uptime_ns')
    ? { label: '状态未知', tone: 'empty' as const, detail: metricEmptyText }
    : uptimeRestarts > 0
      ? { label: '期间有重启', tone: 'warning' as const, detail: '' }
      : { label: '运行正常', tone: 'success' as const, detail: '' };

  const connectionCompare = getPeriodCompare(currentConnections, getLatestChartValue(previousMetricMap.mongodb_connections_current?.viewData || []));
  const throughputCompare = getPeriodCompare(commandsRate, getLatestChartValue(previousMetricMap.mongodb_commands_rate?.viewData || []));
  const cacheCompare = getPeriodCompare(cacheUsageRatio, getLatestChartValue(previousMetricMap.mongodb_wtcache_usage_ratio?.viewData || []));

  const buildThroughputSeries = useMemo(
    () =>
      mergeChartSeries([
        { key: 'mongodb_commands_rate', label: '命令吞吐', displayName: '命令吞吐', data: metricMap.mongodb_commands_rate?.viewData || [] },
        { key: 'mongodb_queries_rate', label: '查询吞吐', displayName: '查询吞吐', data: metricMap.mongodb_queries_rate?.viewData || [] },
        { key: 'mongodb_write_ops_rate', label: '写入吞吐', displayName: '写入吞吐', data: metricMap.mongodb_write_ops_rate?.viewData || [] }
      ]),
    [metricMap.mongodb_commands_rate?.viewData, metricMap.mongodb_queries_rate?.viewData, metricMap.mongodb_write_ops_rate?.viewData]
  );

  const cacheTrendRawData = useMemo(
    () =>
      mergeChartSeries([
        { key: 'mongodb_wtcache_current_bytes', label: '缓存已用', displayName: '缓存已用', data: metricMap.mongodb_wtcache_current_bytes?.viewData || [] },
        { key: 'mongodb_wtcache_max_bytes_configured', label: '缓存上限', displayName: '缓存上限', data: metricMap.mongodb_wtcache_max_bytes_configured?.viewData || [] },
        {
          key: 'mongodb_resident_megabytes',
          label: '常驻内存',
          displayName: '常驻内存',
          data: multiplyChartDataValues(metricMap.mongodb_resident_megabytes?.viewData || [], MEBIBYTE)
        }
      ]),
    [
      metricMap.mongodb_wtcache_current_bytes?.viewData,
      metricMap.mongodb_wtcache_max_bytes_configured?.viewData,
      metricMap.mongodb_resident_megabytes?.viewData
    ]
  );
  const cacheTrendMaxValue = useMemo(
    () =>
      cacheTrendRawData.reduce((max, point) => {
        const values = Object.entries(point)
          .filter(([key, value]) => key.startsWith('value') && typeof value === 'number')
          .map(([, value]) => Number(value));
        return Math.max(max, ...values, 0);
      }, 0),
    [cacheTrendRawData]
  );
  const cacheTrendScale = useMemo(() => resolveDisplayUnit(cacheTrendMaxValue), [cacheTrendMaxValue]);
  const cacheTrendData = useMemo(
    () => scaleChartDataValues(cacheTrendRawData, cacheTrendScale.divisor),
    [cacheTrendRawData, cacheTrendScale.divisor]
  );

  const pressureTrendData = useMemo(
    () =>
      mergeChartSeries([
        { key: 'mongodb_active_reads', label: '活跃读', displayName: '活跃读', data: metricMap.mongodb_active_reads?.viewData || [] },
        { key: 'mongodb_active_writes', label: '活跃写', displayName: '活跃写', data: metricMap.mongodb_active_writes?.viewData || [] },
        { key: 'mongodb_queued_reads', label: '排队读', displayName: '排队读', data: metricMap.mongodb_queued_reads?.viewData || [] },
        { key: 'mongodb_queued_writes', label: '排队写', displayName: '排队写', data: metricMap.mongodb_queued_writes?.viewData || [] }
      ]),
    [
      metricMap.mongodb_active_reads?.viewData,
      metricMap.mongodb_active_writes?.viewData,
      metricMap.mongodb_queued_reads?.viewData,
      metricMap.mongodb_queued_writes?.viewData
    ]
  );

  const networkTrendRawData = useMemo(
    () =>
      mergeChartSeries([
        { key: 'mongodb_net_in_bytes_count_rate', label: '入流量', displayName: '入流量', data: metricMap.mongodb_net_in_bytes_count_rate?.viewData || [] },
        { key: 'mongodb_net_out_bytes_count_rate', label: '出流量', displayName: '出流量', data: metricMap.mongodb_net_out_bytes_count_rate?.viewData || [] }
      ]),
    [metricMap.mongodb_net_in_bytes_count_rate?.viewData, metricMap.mongodb_net_out_bytes_count_rate?.viewData]
  );
  const networkTrendMaxValue = useMemo(
    () =>
      networkTrendRawData.reduce((max, point) => {
        const values = Object.entries(point)
          .filter(([key, value]) => key.startsWith('value') && typeof value === 'number')
          .map(([, value]) => Number(value));
        return Math.max(max, ...values, 0);
      }, 0),
    [networkTrendRawData]
  );
  const networkTrendScale = useMemo(() => resolveDisplayUnit(networkTrendMaxValue, '/s'), [networkTrendMaxValue]);
  const networkTrendData = useMemo(
    () => scaleChartDataValues(networkTrendRawData, networkTrendScale.divisor),
    [networkTrendRawData, networkTrendScale.divisor]
  );

  const pageTitle = displayMode === 'metrics' ? `${objectDisplayText} 全量指标` : 'MongoDB 监控仪表盘';
  const instanceMetaItems = [
    <span key="object-name" className={styles.instanceMetaInline}>{objectDisplayText}</span>,
    <span key="engine" className={styles.instanceMetaInline}>引擎: WiredTiger</span>,
    <span key="timezone" className={styles.instanceMetaInline}>时区: Asia/Shanghai</span>
  ];

  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({ timeRange: val, originValue });
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    if (!arr?.[0] || !arr?.[1]) return;
    const start = dayjs(arr[0]).valueOf();
    const end = dayjs(arr[1]).valueOf();
    if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) return;
    setTimeDefaultValue((prev) => ({ ...prev, rangePickerVaule: arr, selectValue: 0 }));
    setTimeValues({ timeRange: [start, end], originValue: 0 });
  };

  const onFrequenceChange = (val: number) => setFrequence(val);
  const goBack = () => router.push('/monitor/view');

  const onInstanceChange = (value: string) => {
    const target = instanceOptions.find((item) => item.value === value);
    const params = new URLSearchParams(searchParams.toString());
    params.set('instance_id', value);
    params.set('instance_name', String(target?.label || value));
    params.set('instance_id_values', (target?.instanceIdValues || [value]).join(','));
    router.push(`/monitor/view/dashboard/mongodb?${params.toString()}`);
  };

  const getNoDataType = (...metricNames: string[]): 'empty' | 'error' => {
    if (metricNames.includes('mongodb_collection_status')) {
      return collectionStatusMetric?.loadState === 'error' ? 'error' : 'empty';
    }
    const targets = metricNames.map((name) => metricMap[name]).filter(Boolean);
    return targets.length > 0 && targets.every((metric) => metric?.loadState === 'error') ? 'error' : 'empty';
  };

  const uptimeGuide = [
    { label: '运行时长', detail: '基于 mongodb_uptime_ns 计算实例自上次启动以来持续运行的时间。' },
    { label: '启动时间', detail: '用于辅助判断实例是否近期发生过重启。' }
  ];
  const uptimeStateGuide = [
    { label: '状态未知', detail: '当前观察范围内未获取到 mongodb_uptime_ns 指标，暂时无法判断是否发生过重启。' },
    { label: '运行正常', detail: '当前所选时间段内 mongodb_uptime_ns 未出现明显回退。该状态仅表示未观察到重启，不代表实例整体健康度。' },
    { label: '期间有重启', detail: '当前所选时间段内 mongodb_uptime_ns 出现回退，说明实例在该时间段内发生过重启。以上状态仅描述重启观察结果，不代表实例整体健康度。' }
  ];
  const connectionGuide = [
    { label: '当前连接数', detail: '表示当前仍在使用中的客户端连接总量。' },
    { label: '关联判断', detail: '如果当前连接与打开连接同时升高，需要结合排队读写和延迟继续判断是否拥塞。' }
  ];
  const throughputGuide = [
    { label: '命令吞吐', detail: '表示 MongoDB 每秒处理的整体命令速率。' },
    { label: '关联判断', detail: '吞吐抬升时，需要结合缓存使用率、活跃读写和网络流量一起分析来源。' }
  ];
  const latencyGuide = [
    { label: '读延迟', detail: '表示 MongoDB 读请求的平均响应时间。' },
    { label: '关联判断', detail: '读延迟升高时，通常要同时观察缺页频率、排队读写和常驻内存。' }
  ];
  const cacheGuide = [
    { label: '缓存使用率', detail: '表示 WiredTiger 当前已用缓存占配置上限的比例。' },
    { label: '搭配指标', detail: '应同时结合脏数据、常驻内存和缺页频率一起判断缓存是否成为瓶颈。' }
  ];
  const throughputTrendGuide = [
    { label: '吞吐趋势', detail: '同时展示命令吞吐、查询吞吐和写入吞吐，判断当前工作负载类型与变化节奏。' }
  ];
  const cacheTrendGuide = [
    { label: '缓存与内存趋势', detail: '同时展示 WiredTiger 缓存已用、缓存上限和常驻内存，判断缓存与工作集的匹配程度。' }
  ];
  const pressureTrendGuide = [
    { label: '读写压力趋势', detail: '同时展示活跃读写和排队读写，用于判断当前负载是否已开始堆积。' }
  ];
  const networkTrendGuide = [
    { label: '网络流量趋势', detail: '同时展示 MongoDB 网络入流量和出流量，判断请求接收与结果返回的压力。' }
  ];
  const queueGuide = [
    { label: '连接与排队', detail: '展示当前连接、打开连接、可用连接以及读写排队情况。' }
  ];
  const cacheDetailGuide = [
    { label: 'WiredTiger 缓存状态', detail: '展示缓存使用率、缓存上限、脏数据占比与脏数据体量。' }
  ];
  const memoryDetailGuide = [
    { label: '内存与缺页', detail: '展示常驻内存、虚拟内存、已分配内存和缺页频率。' }
  ];
  const networkDetailGuide = [
    { label: '网络与异常', detail: '展示网络流量、游标超时和用户断言，用于判断响应层异常。' }
  ];
  const metricsOverviewGuide = [
    { label: '监控指标全景', detail: '这里承载完整原始监控视图，适合在仪表盘发现异常后继续下钻排查。' }
  ];
  const cachePressureTone =
    cacheUsageRatio >= 90 || cacheDirtyRatio >= 25 ? 'danger' : cacheUsageRatio >= 75 || cacheDirtyRatio >= 12 ? 'warn' : 'normal';
  const queueBacklog = queuedReads + queuedWrites;
  const queueTone = queueBacklog >= 10 ? 'danger' : queueBacklog >= 3 ? 'warn' : 'normal';

  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <div className={styles.pageHeader}>
          <div className={styles.pageTitleRow}>
            <div className={styles.titleBlock}>
              <h1 className={styles.title}>{pageTitle}</h1>
            </div>
            <div className={styles.controlsWrap}>
              <div className={styles.modeTabs}>
                <button type="button" className={`${styles.modeTab} ${displayMode === 'dashboard' ? styles.modeTabActive : ''}`} onClick={() => setDisplayMode('dashboard')}>
                  监控仪表盘
                </button>
                <button type="button" className={`${styles.modeTab} ${displayMode === 'metrics' ? styles.modeTabActive : ''}`} onClick={() => setDisplayMode('metrics')}>
                  全量指标
                </button>
              </div>
              <div className={styles.toolbarTimeSelector}>
                <TimeSelector
                  defaultValue={timeDefaultValue}
                  customFrequencyList={MONGODB_REFRESH_FREQUENCY_LIST}
                  onChange={onTimeChange}
                  onFrequenceChange={onFrequenceChange}
                  onRefresh={() => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))}
                />
              </div>
              <div className={styles.actionButtons}>
                <Button className={styles.toolbarBackBtn} icon={<ArrowLeftOutlined />} onClick={goBack}>返回</Button>
              </div>
            </div>
          </div>

          <div className={`${styles.instanceCard} ${!isDashboardMode ? styles.instanceCardFull : ''}`}>
            <div className={styles.instanceMain}>
              <div className={`${styles.instanceIcon} ${styles.mongoInstanceIcon}`}>
                <DatabaseOutlined />
              </div>
              <div className={styles.instanceInfo}>
                <div className={styles.meta}>
                  <span className={styles.instanceName}>{resolvedInstanceName}</span>
                  {instanceMetaItems.map((item, index) => (
                    <React.Fragment key={index}>
                      <span className={styles.instanceMetaDivider}>|</span>
                      {item}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            </div>
            <div className={styles.instanceActions}>
              <Select
                className={styles.inlineInstanceSelector}
                value={instanceSelectValue}
                loading={instanceLoading}
                options={instanceSelectOptions}
                onChange={onInstanceChange}
                placeholder={resolvedInstanceName !== '--' ? resolvedInstanceName : '选择实例'}
                title={currentInstanceOption?.label || normalizedInstanceName || resolvedInstanceName}
                showSearch
                optionFilterProp="label"
                optionLabelProp="label"
                popupMatchSelectWidth={360}
                filterOption={(input, option) => {
                  const searchText = input.trim().toLowerCase();
                  if (!searchText) return true;
                  const tokens = (option as InstanceOption | undefined)?.searchTokens || [];
                  return tokens.some((token) => token.toLowerCase().includes(searchText));
                }}
                variant="borderless"
              />
            </div>
          </div>
        </div>

        <Spin spinning={loading}>
          {displayMode === 'dashboard' ? (
            <>
              <div className={styles.primaryGrid}>
                <CollectionStatusCard status={collectionStatus} timeline={collectionStatusTimeline} />
                <StatCard
                  title={<TitleWithGuide title="MongoDB 运行时长" items={uptimeGuide} className={styles.statTitleWithGuide} />}
                  value={hasMetricData('mongodb_uptime_ns') ? `${uptimeDisplay.value}${uptimeDisplay.unit}` : '--'}
                  unit=""
                  icon={<ClockCircleOutlined />}
                  iconStyle={{ background: 'rgba(91, 143, 249, 0.12)', color: '#5b8ff9' }}
                  color="#5b8ff9"
                  footer={<span>启动时间 {startupTimeDisplay}</span>}
                  extra={
                    <div
                      className={`${styles.uptimeStatus} ${
                        styles[`uptimeStatus${uptimeState.tone === 'success' ? 'Success' : uptimeState.tone === 'warning' ? 'Warning' : 'Empty'}`]
                      }`}
                    >
                      <span className={styles.uptimeStatusDot} />
                      <span className={styles.uptimeStatusMainWrap}>
                        <span className={styles.uptimeStatusMain}>{uptimeState.label}</span>
                        <Tooltip
                          overlayClassName="lightMetricTooltip"
                          title={
                            <div className={styles.uptimeStatusTooltip}>
                              {uptimeStateGuide.map((item) => (
                                <div key={item.label} className={styles.uptimeStatusTooltipRow}>
                                  <strong>{item.label}</strong>
                                  <span>{item.detail}</span>
                                </div>
                              ))}
                            </div>
                          }
                        >
                          <ClockCircleOutlined className={styles.uptimeStatusInfoIcon} />
                        </Tooltip>
                      </span>
                      {uptimeState.detail ? <span className={styles.uptimeStatusDetail}>{uptimeState.detail}</span> : null}
                    </div>
                  }
                  hideTrend
                  className={styles.statCardRelaxed}
                  bodyClassName={styles.statBodyRelaxed}
                  noDataType={getNoDataType('mongodb_uptime_ns')}
                />
                <StatCard
                  title={<TitleWithGuide title="当前连接数" items={connectionGuide} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_connections_current', connectionsDisplay.value)}
                  unit=""
                  icon={<NodeIndexOutlined />}
                  iconStyle={{ background: 'rgba(47, 107, 255, 0.12)', color: '#2f6bff' }}
                  color="#2f6bff"
                  footer={
                    <>
                      <span>可用 {renderMetricValue('mongodb_connections_available', formatMetricValue(availableConnections, 'counts').value)}</span>
                      <span>打开 {renderMetricValue('mongodb_open_connections', formatMetricValue(openConnections, 'counts').value)}</span>
                    </>
                  }
                  compare={connectionCompare}
                  trendData={metricMap.mongodb_connections_current?.viewData || []}
                  noDataType={getNoDataType('mongodb_connections_current')}
                />
                <StatCard
                  title={<TitleWithGuide title="命令吞吐" items={throughputGuide} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_commands_rate', commandsDisplay.value)}
                  unit={hasMetricData('mongodb_commands_rate') ? commandsDisplay.unit : ''}
                  icon={<ThunderboltOutlined />}
                  iconStyle={{ background: 'rgba(39, 194, 116, 0.12)', color: '#27c274' }}
                  color="#27c274"
                  footer={
                    <>
                      <span>查询 {renderMetricValue('mongodb_queries_rate', `${queriesDisplay.value}${queriesDisplay.unit}`)}</span>
                      <span>写入 {renderMetricValue('mongodb_write_ops_rate', `${writesDisplay.value}${writesDisplay.unit}`)}</span>
                    </>
                  }
                  compare={throughputCompare}
                  trendData={metricMap.mongodb_commands_rate?.viewData || []}
                  noDataType={getNoDataType('mongodb_commands_rate')}
                />
                <StatCard
                  title={<TitleWithGuide title="读延迟" items={latencyGuide} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_latency_reads_avg', readLatencyDisplay.value)}
                  unit={hasMetricData('mongodb_latency_reads_avg') ? readLatencyDisplay.unit : ''}
                  icon={<ClockCircleOutlined />}
                  iconStyle={{ background: 'rgba(255, 159, 67, 0.12)', color: '#ff9f43' }}
                  color="#ff9f43"
                  footer={
                    <>
                      <span>命令延迟 {renderMetricValue('mongodb_latency_commands_avg', `${commandLatencyDisplay.value}${commandLatencyDisplay.unit}`)}</span>
                      <span>缺页 {renderMetricValue('mongodb_page_faults_rate', `${pageFaultDisplay.value}${pageFaultDisplay.unit}`)}</span>
                    </>
                  }
                  trendData={metricMap.mongodb_latency_reads_avg?.viewData || []}
                  noDataType={getNoDataType('mongodb_latency_reads_avg')}
                />
                <StatCard
                  title={<TitleWithGuide title="WiredTiger 缓存使用率" items={cacheGuide} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_wtcache_usage_ratio', cacheUsageDisplay.value)}
                  unit={hasMetricData('mongodb_wtcache_usage_ratio') ? cacheUsageDisplay.unit : ''}
                  icon={<DatabaseOutlined />}
                  iconStyle={{ background: 'rgba(47, 107, 255, 0.12)', color: '#2f6bff' }}
                  color="#2f6bff"
                  footer={
                    <>
                      <span>已用 {renderMetricValue('mongodb_wtcache_current_bytes', `${cacheCurrentDisplay.value}${cacheCurrentDisplay.unit}`)}</span>
                      <span>脏数据 {renderMetricValue('mongodb_wtcache_tracked_dirty_bytes', `${cacheDirtyDisplay.value}${cacheDirtyDisplay.unit}`)}</span>
                    </>
                  }
                  compare={cacheCompare}
                  trendData={metricMap.mongodb_wtcache_usage_ratio?.viewData || []}
                  noDataType={getNoDataType('mongodb_wtcache_usage_ratio')}
                />
              </div>

              <div className={styles.mainTrendGrid}>
                <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                  <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                    <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
                      <TitleWithGuide title="吞吐趋势" items={throughputTrendGuide} className={styles.panelTitleWithGuide} />
                    </h3>
                    <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>命令、查询与写入变化</div>
                    <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                      {TREND_LEGENDS.throughput.map((item) => (
                        <span key={item.label} className={styles.chartLegendItem}>
                          <span className={styles.chartLegendDot} style={{ background: item.color }} />
                          {item.label}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className={styles.chartWrap}>
                    <LineChart
                      data={buildThroughputSeries}
                      metric={buildMetricItem(metricMap.mongodb_commands_rate || { ...DASHBOARD_METRICS[4], viewData: [], loadState: 'success' })}
                      seriesStyles={TREND_LEGENDS.throughput.map((item) => ({ color: item.color, unit: 'ops/s' }))}
                      allowSelect={false}
                      onXRangeChange={onXRangeChange}
                    />
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                  <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                    <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
                      <TitleWithGuide title="缓存与内存趋势" items={cacheTrendGuide} className={styles.panelTitleWithGuide} />
                    </h3>
                    <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>缓存已用、缓存上限与常驻内存</div>
                    <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                      {TREND_LEGENDS.cache.map((item) => (
                        <span key={item.label} className={styles.chartLegendItem}>
                          <span
                            className={item.dashed ? styles.chartLegendDash : styles.chartLegendDot}
                            style={item.dashed ? { borderTopColor: item.color } : { background: item.color }}
                          />
                          {item.label}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className={styles.chartWrap}>
                    <LineChart
                      data={cacheTrendData}
                      unit={cacheTrendScale.label}
                      metric={buildMetricItem(metricMap.mongodb_wtcache_current_bytes || { ...DASHBOARD_METRICS[17], viewData: [], loadState: 'success' })}
                      seriesStyles={[
                        { color: TREND_LEGENDS.cache[0].color, unit: cacheTrendScale.label },
                        { color: TREND_LEGENDS.cache[1].color, strokeDasharray: '5 5', unit: cacheTrendScale.label },
                        { color: TREND_LEGENDS.cache[2].color, unit: cacheTrendScale.label }
                      ]}
                      allowSelect={false}
                      onXRangeChange={onXRangeChange}
                    />
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                  <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                    <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
                      <TitleWithGuide title="读写压力趋势" items={pressureTrendGuide} className={styles.panelTitleWithGuide} />
                    </h3>
                    <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>活跃读写与排队读写</div>
                    <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                      {TREND_LEGENDS.pressure.map((item) => (
                        <span key={item.label} className={styles.chartLegendItem}>
                          <span className={styles.chartLegendDot} style={{ background: item.color }} />
                          {item.label}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className={styles.chartWrap}>
                    <LineChart
                      data={pressureTrendData}
                      metric={buildMetricItem(metricMap.mongodb_active_reads || { ...DASHBOARD_METRICS[10], viewData: [], loadState: 'success' })}
                      seriesStyles={TREND_LEGENDS.pressure.map((item) => ({ color: item.color, unit: 'counts' }))}
                      allowSelect={false}
                      onXRangeChange={onXRangeChange}
                    />
                  </div>
                </div>
              </div>

              <div className={styles.detailGrid}>
                <div className={`${styles.panel} ${styles.quarterPanel}`}>
                  <div className={styles.detailCard}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}><TitleWithGuide title="连接与排队" items={queueGuide} className={styles.panelTitleWithGuide} /></h3>
                      <div className={styles.panelSubTitle}>连接容量与等待积压</div>
                    </div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>当前连接</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_connections_current', formatMetricValue(currentConnections, 'counts').value)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>打开连接</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_open_connections', formatMetricValue(openConnections, 'counts').value)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>排队读操作</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_queued_reads', formatMetricValue(queuedReads, 'counts').value)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>排队写操作</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_queued_writes', formatMetricValue(queuedWrites, 'counts').value)}</span></div>
                    <div className={`${styles.fragmentationWarning} ${queueTone === 'danger' ? styles.fragmentationWarningDanger : queueTone === 'warn' ? styles.fragmentationWarningWarn : styles.fragmentationWarningNormal}`}>
                      {queueTone === 'danger' ? '读写队列已明显堆积，建议优先排查缓存与内存压力。' : queueTone === 'warn' ? '已出现轻微排队，需要结合延迟和缺页持续观察。' : '当前未观察到明显排队堆积。'}
                    </div>
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.quarterPanel}`}>
                  <div className={styles.detailCard}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}><TitleWithGuide title="WiredTiger 缓存状态" items={cacheDetailGuide} className={styles.panelTitleWithGuide} /></h3>
                      <div className={styles.panelSubTitle}>缓存占用与脏数据状态</div>
                    </div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>缓存使用率</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_wtcache_usage_ratio', `${cacheUsageDisplay.value}${cacheUsageDisplay.unit}`)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>脏数据占比</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_wtcache_dirty_ratio', `${cacheDirtyRatioDisplay.value}${cacheDirtyRatioDisplay.unit}`)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>缓存上限</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_wtcache_max_bytes_configured', `${cacheMaxDisplay.value}${cacheMaxDisplay.unit}`)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>脏数据大小</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_wtcache_tracked_dirty_bytes', `${cacheDirtyDisplay.value}${cacheDirtyDisplay.unit}`)}</span></div>
                    <div className={`${styles.fragmentationWarning} ${cachePressureTone === 'danger' ? styles.fragmentationWarningDanger : cachePressureTone === 'warn' ? styles.fragmentationWarningWarn : styles.fragmentationWarningNormal}`}>
                      {cachePressureTone === 'danger' ? '缓存接近饱和或脏数据偏高，优先排查工作集与落盘压力。' : cachePressureTone === 'warn' ? '缓存利用率开始升高，需要同时观察常驻内存与缺页。' : '当前缓存状态平稳。'}
                    </div>
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.quarterPanel}`}>
                  <div className={styles.detailCard}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}><TitleWithGuide title="内存与缺页" items={memoryDetailGuide} className={styles.panelTitleWithGuide} /></h3>
                      <div className={styles.panelSubTitle}>工作集与进程内存匹配</div>
                    </div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>常驻内存</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_resident_megabytes', `${residentDisplay.value}${residentDisplay.unit}`)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>虚拟内存</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_vsize_megabytes', `${virtualDisplay.value}${virtualDisplay.unit}`)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>已分配内存</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_tcmalloc_current_allocated_bytes', `${allocatedDisplay.value}${allocatedDisplay.unit}`)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>缺页频率</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_page_faults_rate', `${pageFaultDisplay.value}${pageFaultDisplay.unit}`)}</span></div>
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.quarterPanel}`}>
                  <div className={styles.detailCard}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}><TitleWithGuide title="网络与异常" items={networkDetailGuide} className={styles.panelTitleWithGuide} /></h3>
                      <div className={styles.panelSubTitle}>结果返回与异常信号</div>
                    </div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>入流量</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_net_in_bytes_count_rate', `${netInDisplay.value}${netInDisplay.unit}`)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>出流量</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_net_out_bytes_count_rate', `${netOutDisplay.value}${netOutDisplay.unit}`)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>游标超时数</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_cursor_timed_out_count', formatMetricValue(cursorTimedOut, 'counts').value)}</span></div>
                    <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>用户断言</span><span className={styles.detailMetricValue}>{renderMetricValue('mongodb_assert_user', formatMetricValue(userAssert, 'counts').value)}</span></div>
                  </div>
                </div>
              </div>

              <div className={styles.mainTrendGrid}>
                <div className={`${styles.panel} ${styles.fullPanel}`}>
                  <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                    <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
                      <TitleWithGuide title="网络流量趋势" items={networkTrendGuide} className={styles.panelTitleWithGuide} />
                    </h3>
                    <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>入流量与出流量</div>
                    <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                      {TREND_LEGENDS.network.map((item) => (
                        <span key={item.label} className={styles.chartLegendItem}>
                          <span className={styles.chartLegendDot} style={{ background: item.color }} />
                          {item.label}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className={styles.chartWrap}>
                    <LineChart
                      data={networkTrendData}
                      unit={networkTrendScale.label}
                      metric={buildMetricItem(metricMap.mongodb_net_in_bytes_count_rate || { ...DASHBOARD_METRICS[22], viewData: [], loadState: 'success' })}
                      seriesStyles={[
                        { color: TREND_LEGENDS.network[0].color, unit: networkTrendScale.label },
                        { color: TREND_LEGENDS.network[1].color, unit: networkTrendScale.label }
                      ]}
                      allowSelect={false}
                      onXRangeChange={onXRangeChange}
                    />
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className={`${styles.modeContent} ${styles.metricsMode}`}>
              <div className={`${styles.panel} ${styles.fullPanel}`}>
                <div className={styles.panelHeader}>
                  <div className={styles.panelHeading}>
                    <h3 className={styles.panelTitle}>
                      <TitleWithGuide title="监控指标全景" items={metricsOverviewGuide} className={styles.panelTitleWithGuide} />
                    </h3>
                  </div>
                </div>
                <MetricViews
                  key={`${monitorObjectId}-${instanceId}-${idValues.join('|')}`}
                  monitorObjectId={monitorObjectId}
                  monitorObjectName={monitorObjectName}
                  instanceId={String(instanceId)}
                  instanceName={instanceName}
                  idValues={idValues}
                  externalTimeValues={timeValues}
                  externalTimeDefaultValue={timeDefaultValue}
                  externalFrequence={frequence}
                  externalRefreshSignal={metricsRefreshSignal}
                  hideTimeSelector
                  onExternalXRangeChange={onXRangeChange}
                />
              </div>
            </div>
          )}
        </Spin>
      </div>
    </div>
  );
}
