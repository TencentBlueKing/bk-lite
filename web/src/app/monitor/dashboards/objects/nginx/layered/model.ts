import { CHART_COLORS } from '@/app/monitor/constants';
import type { ChartData } from '@/app/monitor/types';
import {
  byteScale,
  COLLECTION_OK,
  EMPTY_READING,
  formatBytesPerSecond,
  formatCount,
  formatDuration,
  formatPercent,
  formatPerSecond,
  NOT_ONBOARDED,
  pickDurationUnit,
  type DurationUnit
} from './format';
import {
  busyRatio,
  collectionKind,
  droppedRate,
  freshLimitSeconds,
  handledRatio,
  isStale,
  mergeSourceTime,
  waitingRatio,
  type CollectionKind
} from './freshness';

export interface Point {
  time: number;
  value: number;
}

export interface RangeSeries {
  name: string;
  labels: Record<string, string>;
  points: Point[];
}

export interface InstantSample {
  labels: Record<string, string>;
  /** tlast_over_time 的 value[1]，或能力探测的样本值。 */
  value: number;
}

export interface NginxQueryResult {
  range: Record<string, RangeSeries[]>;
  instant: Record<string, InstantSample[]>;
}

const labelOf = (labels: Record<string, string> | undefined, key: string) => (
  String(labels?.[key] ?? '')
);

export const readRangeSeries = (result: unknown): RangeSeries[] => {
  const rows = (result as { data?: { result?: unknown[] } } | null)?.data?.result;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    const record = row as { metric?: Record<string, string>; values?: unknown[]; value?: unknown[] };
    const labels = record.metric && typeof record.metric === 'object' ? { ...record.metric } : {};
    const rawPoints = Array.isArray(record.values)
      ? record.values
      : (Array.isArray(record.value) ? [record.value] : []);
    const points = rawPoints.flatMap((pair) => {
      if (!Array.isArray(pair) || pair.length < 2) return [];
      const time = Number(pair[0]);
      const value = Number(pair[1]);
      if (!Number.isFinite(time) || !Number.isFinite(value)) return [];
      return [{ time, value }];
    }).sort((left, right) => left.time - right.time);
    if (!points.length) return [];
    return [{ name: String(labels.__name__ || ''), labels, points }];
  });
};

export const readInstantSamples = (result: unknown): InstantSample[] => {
  const rows = (result as { data?: { result?: unknown[] } } | null)?.data?.result;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    const record = row as { metric?: Record<string, string>; value?: unknown[] };
    const raw = record.value;
    if (!Array.isArray(raw) || raw.length < 2) return [];
    const value = Number(raw[1]);
    if (!Number.isFinite(value)) return [];
    const labels = record.metric && typeof record.metric === 'object' ? { ...record.metric } : {};
    return [{ labels, value }];
  });
};

const latestPoint = (points: readonly Point[]) => (
  points.length ? points[points.length - 1].value : null
);

const byLabel = (series: readonly RangeSeries[], key: string, value: string) => (
  series.find((item) => labelOf(item.labels, key) === value)
);

const pointsOf = (series: RangeSeries | undefined) => series?.points ?? [];

export const chartRows = (series: ReadonlyArray<{ points: readonly Point[] }>): ChartData[] => {
  const times = new Set<number>();
  series.forEach((item) => item.points.forEach((point) => times.add(point.time)));
  return Array.from(times).sort((left, right) => left - right).map((time) => {
    const row: ChartData = { time };
    series.forEach((item, index) => {
      const found = item.points.find((point) => point.time === time);
      if (found) row[`value${String(index + 1).padStart(2, '0')}`] = found.value;
    });
    return row;
  });
};

const sourceTime = (
  samples: readonly InstantSample[],
  now: number,
  match: (labels: Record<string, string>) => boolean
) => mergeSourceTime(samples.filter((sample) => match(sample.labels)), now);

const matchesMetric = (labels: Record<string, string>, metricName: string) => (
  labelOf(labels, '__name__') === metricName || labelOf(labels, 'metric') === metricName
);

const namedFresh = (
  samples: readonly InstantSample[],
  now: number,
  limit: number,
  metricName: string,
  extra?: (labels: Record<string, string>) => boolean
) => isStale(sourceTime(samples, now, (labels) => (
  matchesMetric(labels, metricName) && (extra ? extra(labels) : true)
)), now, limit);

const freshValue = (value: number | null, stale: boolean) => (
  stale ? null : value
);

const CODE_COLORS: Record<string, string> = {
  '1xx': '#8c8c8c',
  '2xx': '#27c274',
  '3xx': '#2f6bff',
  '4xx': '#ff8a1f',
  '5xx': '#ff4d4f'
};

const colorAt = (index: number) => CHART_COLORS[index % CHART_COLORS.length] || '#2f6bff';

export interface NginxSeriesItem {
  id: string;
  label: string;
  color: string;
  points: Point[];
  reading: string;
}

export interface ZoneTableRow {
  zone: string;
  requestRate: number | null;
  codes: Record<string, number | null>;
  bytesIn: number | null;
  bytesOut: number | null;
  timeMs: number | null;
}

export interface UpstreamMemberRow {
  upstream: string;
  address: string;
  requestRate: number | null;
  codes: Record<string, number | null>;
  bytesIn: number | null;
  bytesOut: number | null;
  requestMs: number | null;
  responseMs: number | null;
  down: number | null;
  backup: number | null;
  weight: number | null;
  maxFails: number | null;
  failTimeout: number | null;
}

export interface UpstreamGroupRow {
  upstream: string;
  requestRate: number | null;
  codes: Record<string, number | null>;
  bytesIn: number | null;
  bytesOut: number | null;
  members: UpstreamMemberRow[];
}

export interface FilterTableRow {
  filterName: string;
  filterKey: string;
  requestRate: number | null;
  codes: Record<string, number | null>;
  bytesIn: number | null;
  bytesOut: number | null;
  timeMs: number | null;
}

export interface NginxDashboardModel {
  collection: { kind: CollectionKind; label: string; tone?: string };
  request: string;
  accepts: string;
  handledRate: string;
  active: string;
  dropped: string;
  handled: string;
  busy: string;
  waiting: string;
  alertReady: boolean;
  requestPoints: Point[];
  acceptPoints: Point[];
  handledPoints: Point[];
  droppedPoints: Point[];
  connSeries: NginxSeriesItem[];
  busyPoints: Point[];
  waitingPoints: Point[];
  ring: { active: number | null; reading: number | null; writing: number | null; waiting: number | null };
  requestTotal: string | null;
  showRequestTime: boolean;
  requestTime: string;
  requestTimePoints: Point[];
  requestTimeUnit: DurationUnit;
  focus: {
    requestValue: string;
    requestDetail: string;
    requestTab: 'sites' | null;
    connectionValue: string;
    connectionDetail: string;
    dropValue: string;
    dropDetail: string;
    fourthTitle: string;
    fourthValue: string;
    fourthDetail: string;
    fourthTab: 'sites' | 'upstream' | 'connections';
  };
  tabs: { sites: boolean; upstream: boolean };
  showFilter: boolean;
  zoneRequest: NginxSeriesItem[];
  zoneStatus: NginxSeriesItem[];
  zoneBytes: NginxSeriesItem[];
  zoneTime: NginxSeriesItem[];
  zoneTimeUnit: DurationUnit;
  byteScaleDiv: number;
  byteSuffix: string;
  zoneRows: ZoneTableRow[];
  zoneSummary: ZoneTableRow | null;
  upstreamRequest: NginxSeriesItem[];
  upstreamStatus: NginxSeriesItem[];
  upstreamRequestTime: NginxSeriesItem[];
  upstreamResponseTime: NginxSeriesItem[];
  upstreamTimeUnit: DurationUnit;
  upstreamGroups: UpstreamGroupRow[];
  upstreamDownOnly: boolean;
  filterRequest: NginxSeriesItem[];
  filterRows: FilterTableRow[];
}

const EMPTY_FOCUS = {
  requestValue: EMPTY_READING,
  requestDetail: '窗口内的请求速率',
  requestTab: null as 'sites' | null,
  connectionValue: EMPTY_READING,
  connectionDetail: '读取、写入和等待的结构',
  dropValue: EMPTY_READING,
  dropDetail: '丢弃速率和完成率',
  fourthTitle: '等待连接占比',
  fourthValue: EMPTY_READING,
  fourthDetail: '空闲等待占活跃连接的比例',
  fourthTab: 'connections' as const
};

const emptyModel = (kind: CollectionKind, label: string): NginxDashboardModel => ({
  collection: { kind, label },
  request: EMPTY_READING,
  accepts: EMPTY_READING,
  handledRate: EMPTY_READING,
  active: EMPTY_READING,
  dropped: EMPTY_READING,
  handled: EMPTY_READING,
  busy: EMPTY_READING,
  waiting: EMPTY_READING,
  alertReady: true,
  requestPoints: [],
  acceptPoints: [],
  handledPoints: [],
  droppedPoints: [],
  connSeries: [],
  busyPoints: [],
  waitingPoints: [],
  ring: { active: null, reading: null, writing: null, waiting: null },
  requestTotal: null,
  showRequestTime: false,
  requestTime: EMPTY_READING,
  requestTimePoints: [],
  requestTimeUnit: 'ms',
  focus: EMPTY_FOCUS,
  tabs: { sites: false, upstream: false },
  showFilter: false,
  zoneRequest: [],
  zoneStatus: [],
  zoneBytes: [],
  zoneTime: [],
  zoneTimeUnit: 'ms',
  byteScaleDiv: 1,
  byteSuffix: '字节/秒',
  zoneRows: [],
  zoneSummary: null,
  upstreamRequest: [],
  upstreamStatus: [],
  upstreamRequestTime: [],
  upstreamResponseTime: [],
  upstreamTimeUnit: 'ms',
  upstreamGroups: [],
  upstreamDownOnly: false,
  filterRequest: [],
  filterRows: []
});

const alignBinary = (
  left: readonly Point[],
  right: readonly Point[],
  combine: (leftValue: number, rightValue: number) => number | null
) => {
  const rightByTime = new Map(right.map((point) => [point.time, point.value]));
  return left.flatMap((point) => {
    const other = rightByTime.get(point.time);
    if (other == null) return [];
    const value = combine(point.value, other);
    if (value == null || !Number.isFinite(value)) return [];
    return [{ time: point.time, value }];
  });
};

const requestShape = (points: readonly Point[], stale: boolean) => {
  if (stale || points.length < 2) return 'empty' as const;
  const latest = points[points.length - 1].value;
  const earlier = points.slice(0, -1);
  const average = earlier.reduce((sum, point) => sum + point.value, 0) / earlier.length;
  if (average > 0 && latest >= average * 2 && latest - average >= 1) return 'up' as const;
  if (average >= 1 && latest <= average * 0.5) return 'down' as const;
  return 'steady' as const;
};

const seriesItem = (
  id: string,
  label: string,
  color: string,
  points: Point[],
  reading: string
): NginxSeriesItem => ({ id, label, color, points, reading });

const durationItems = (
  rows: ReadonlyArray<{ id: string; label: string; points: Point[]; fresh: boolean }>,
  unit: DurationUnit
) => rows.map((row, index) => seriesItem(
  row.id,
  row.label,
  colorAt(index),
  row.points,
  row.fresh ? formatDuration(latestPoint(row.points) ?? Number.NaN, unit) : EMPTY_READING
));

const sumByCode = (series: readonly RangeSeries[]) => {
  const codes = new Map<string, Map<number, number>>();
  series.forEach((item) => {
    const code = labelOf(item.labels, 'code');
    if (!code || code === 'total') return;
    const bucket = codes.get(code) ?? new Map<number, number>();
    item.points.forEach((point) => {
      bucket.set(point.time, (bucket.get(point.time) ?? 0) + point.value);
    });
    codes.set(code, bucket);
  });
  return Array.from(codes.entries()).map(([code, bucket]) => ({
    code,
    points: Array.from(bucket.entries()).map(([time, value]) => ({ time, value })).sort((left, right) => left.time - right.time)
  }));
};

const hasFinite = (value: number | null | undefined) => value != null && Number.isFinite(value);

const sortNullLast = (left: number | null, right: number | null) => {
  if (!hasFinite(left) && !hasFinite(right)) return 0;
  if (!hasFinite(left)) return 1;
  if (!hasFinite(right)) return -1;
  return (right as number) - (left as number);
};

export const buildNginxDashboard = ({
  onboarded,
  nowSeconds,
  intervalSeconds,
  data,
  sitesEnabled,
  upstreamEnabled
}: {
  onboarded: boolean;
  nowSeconds: number;
  intervalSeconds?: number;
  data: NginxQueryResult;
  sitesEnabled?: boolean;
  upstreamEnabled?: boolean;
}): NginxDashboardModel => {
  const limit = freshLimitSeconds(intervalSeconds);
  if (!onboarded) return emptyModel('not_onboarded', NOT_ONBOARDED);

  const stubFresh = data.instant.stubFresh ?? [];
  const serverFresh = data.instant.serverFresh ?? [];
  const upstreamFresh = data.instant.upstreamFresh ?? [];
  const activeSource = sourceTime(stubFresh, nowSeconds, (labels) => matchesMetric(labels, 'nginx_active'));
  const kind = collectionKind(true, activeSource, nowSeconds, limit);
  const collectionLabel = kind === 'success'
    ? COLLECTION_OK
    : kind === 'expired'
      ? '暂无数据（已过期）'
      : EMPTY_READING;

  const conn = data.range.conn ?? [];
  const gauge = (status: string) => pointsOf(byLabel(conn, 'status', status));
  const activePoints = gauge('active');
  const readingPoints = gauge('reading');
  const writingPoints = gauge('writing');
  const waitingPoints = gauge('waiting');
  const activeStale = namedFresh(stubFresh, nowSeconds, limit, 'nginx_active');
  const readingStale = namedFresh(stubFresh, nowSeconds, limit, 'nginx_reading');
  const writingStale = namedFresh(stubFresh, nowSeconds, limit, 'nginx_writing');
  const waitingStale = namedFresh(stubFresh, nowSeconds, limit, 'nginx_waiting');
  const activeNow = freshValue(latestPoint(activePoints), activeStale);
  const readingNow = freshValue(latestPoint(readingPoints), readingStale);
  const writingNow = freshValue(latestPoint(writingPoints), writingStale);
  const waitingNow = freshValue(latestPoint(waitingPoints), waitingStale);

  const requestPoints = pointsOf(data.range.requestsRate?.[0]);
  const acceptPoints = pointsOf(data.range.acceptsRate?.[0]);
  const handledPoints = pointsOf(data.range.handledRate?.[0]);
  const requestStale = namedFresh(stubFresh, nowSeconds, limit, 'nginx_requests');
  const acceptStale = namedFresh(stubFresh, nowSeconds, limit, 'nginx_accepts');
  const handledStale = namedFresh(stubFresh, nowSeconds, limit, 'nginx_handled');
  const requestNow = freshValue(latestPoint(requestPoints), requestStale);
  const acceptNow = freshValue(latestPoint(acceptPoints), acceptStale);
  const handledNow = freshValue(latestPoint(handledPoints), handledStale);
  const rateStale = acceptStale || handledStale;
  const droppedNow = droppedRate(acceptNow, handledNow, rateStale);
  const handledShare = handledRatio(acceptNow, handledNow, rateStale);
  const busyNow = busyRatio(activeNow, readingNow, writingNow, activeStale || readingStale || writingStale);
  const waitingShare = waitingRatio(activeNow, waitingNow, activeStale || waitingStale);
  const totalPoints = pointsOf(data.range.requestsTotal?.[0]);
  const totalNow = freshValue(latestPoint(totalPoints), requestStale);

  const droppedPoints = alignBinary(acceptPoints, handledPoints, (accepts, handled) => Math.max(accepts - handled, 0));
  const busyPoints = alignBinary(readingPoints, writingPoints, (reading, writing) => reading + writing)
    .flatMap((sum) => {
      const active = activePoints.find((point) => point.time === sum.time);
      if (!active || active.value === 0) return [];
      return [{ time: sum.time, value: (sum.value / active.value) * 100 }];
    });
  const waitingRatioPoints = alignBinary(waitingPoints, activePoints, (waiting, active) => (
    active === 0 ? null : (waiting / active) * 100
  ));

  const connSeries: NginxSeriesItem[] = [
    ['active', '活跃连接', '#2f6bff', activePoints, activeNow, '个'],
    ['reading', '读取连接', '#27c274', readingPoints, readingNow, '个'],
    ['writing', '写入连接', '#ff8a1f', writingPoints, writingNow, '个'],
    ['waiting', '等待连接', '#8a5cff', waitingPoints, waitingNow, '个']
  ].map(([id, label, color, points, value, unit]) => seriesItem(
    String(id),
    String(label),
    String(color),
    points as Point[],
    value == null ? EMPTY_READING : formatCount(value as number, String(unit))
  ));

  const sites = sitesEnabled ?? (data.instant.serverCap?.length ?? 0) > 0;
  const upstream = upstreamEnabled ?? (data.instant.upstreamCap?.length ?? 0) > 0;
  const showFilter = (data.instant.filterCap?.length ?? 0) > 0;

  const zoneFresh = (metric: string, zone: string) => !namedFresh(
    serverFresh,
    nowSeconds,
    limit,
    metric,
    (labels) => labelOf(labels, 'zone') === zone
  );

  const zoneRequestSeries = (data.range.zoneRequestRate ?? [])
    .filter((item) => labelOf(item.labels, 'zone') && labelOf(item.labels, 'zone') !== '*')
    .sort((left, right) => labelOf(left.labels, 'zone').localeCompare(labelOf(right.labels, 'zone')));
  const zoneRequest = zoneRequestSeries.map((item, index) => {
    const zone = labelOf(item.labels, 'zone');
    const fresh = zoneFresh('nginx_vts_server_requests', zone);
    const value = fresh ? latestPoint(item.points) : null;
    return seriesItem(zone, zone, colorAt(index), item.points, value == null ? EMPTY_READING : formatPerSecond(value, '次'));
  });

  const statusOrder = ['1xx', '2xx', '3xx', '4xx', '5xx'];
  const zoneStatus = sumByCode(data.range.zoneStatusRate ?? [])
    .sort((left, right) => statusOrder.indexOf(left.code) - statusOrder.indexOf(right.code))
    .map((item) => {
      const parts = (data.range.zoneStatusRate ?? []).filter((series) => labelOf(series.labels, 'code') === item.code);
      const stale = parts.some((series) => !zoneFresh(`nginx_vts_server_response_${item.code}_count`, labelOf(series.labels, 'zone')));
      const value = stale ? null : latestPoint(item.points);
      return seriesItem(
        item.code,
        item.code,
        CODE_COLORS[item.code] || colorAt(0),
        item.points,
        value == null ? EMPTY_READING : formatPerSecond(value, '次')
      );
    });

  const bytePeak = (data.range.zoneBytes ?? []).reduce((peak, item) => (
    Math.max(peak, ...item.points.map((point) => Math.abs(point.value)))
  ), 0);
  const scale = byteScale(bytePeak);
  const zoneBytes = (data.range.zoneBytes ?? [])
    .filter((item) => labelOf(item.labels, 'zone') && labelOf(item.labels, 'zone') !== '*')
    .map((item) => ({
      zone: labelOf(item.labels, 'zone'),
      direction: labelOf(item.labels, 'direction'),
      points: item.points
    }))
    .sort((left, right) => `${left.zone}${left.direction}`.localeCompare(`${right.zone}${right.direction}`))
    .map((item, index) => {
      const freshMetric = item.direction === 'out' ? 'nginx_vts_server_out_bytes' : 'nginx_vts_server_in_bytes';
      const fresh = zoneFresh(freshMetric, item.zone);
      const value = fresh ? latestPoint(item.points) : null;
      const directionLabel = item.direction === 'out' ? '出站' : '入站';
      return seriesItem(
        `${item.zone}|${item.direction}`,
        `${item.zone} ${directionLabel}`,
        colorAt(index),
        item.points,
        value == null ? EMPTY_READING : formatBytesPerSecond(value, scale)
      );
    });

  const timeRows = (data.range.zoneTime ?? [])
    .filter((item) => labelOf(item.labels, 'zone') && labelOf(item.labels, 'zone') !== '*')
    .map((item) => ({
      id: labelOf(item.labels, 'zone'),
      label: labelOf(item.labels, 'zone'),
      points: item.points,
      fresh: zoneFresh('nginx_vts_server_request_time', labelOf(item.labels, 'zone'))
    }))
    .sort((left, right) => left.label.localeCompare(right.label));
  const zoneTimePeak = timeRows.reduce((peak, item) => Math.max(peak, ...item.points.map((point) => Math.abs(point.value))), 0);
  const zoneTimeUnit = pickDurationUnit(zoneTimePeak);
  const zoneTime = durationItems(timeRows, zoneTimeUnit);

  const starTime = data.range.starTime ?? [];
  const showRequestTime = starTime.some((item) => item.points.length > 0);
  const starTimePoints = starTime[0]?.points ?? [];
  const starTimeFresh = zoneFresh('nginx_vts_server_request_time', '*');
  const requestTimeUnit = pickDurationUnit(Math.max(...starTimePoints.map((point) => Math.abs(point.value)), 0));

  const codeValue = (series: readonly RangeSeries[], zone: string, code: string, metric: string) => {
    const found = series.find((item) => labelOf(item.labels, 'zone') === zone && labelOf(item.labels, 'code') === code);
    if (!found || !zoneFresh(metric, zone)) return null;
    return latestPoint(found.points);
  };
  const byteValue = (series: readonly RangeSeries[], zone: string, direction: string, metric: string) => {
    const found = series.find((item) => labelOf(item.labels, 'zone') === zone && labelOf(item.labels, 'direction') === direction);
    if (!found || !zoneFresh(metric, zone)) return null;
    return latestPoint(found.points);
  };
  const zones = new Set<string>();
  (data.range.zoneRequestRate ?? []).forEach((item) => {
    const zone = labelOf(item.labels, 'zone');
    if (zone && zone !== '*') zones.add(zone);
  });
  (data.range.zoneStatusRate ?? []).forEach((item) => {
    const zone = labelOf(item.labels, 'zone');
    if (zone && zone !== '*') zones.add(zone);
  });
  (data.range.zoneBytes ?? []).forEach((item) => {
    const zone = labelOf(item.labels, 'zone');
    if (zone && zone !== '*') zones.add(zone);
  });
  timeRows.forEach((item) => zones.add(item.id));

  const zoneRows = Array.from(zones).map((zone) => {
    const request = zoneRequestSeries.find((item) => labelOf(item.labels, 'zone') === zone);
    const time = timeRows.find((item) => item.id === zone);
    return {
      zone,
      requestRate: request && zoneFresh('nginx_vts_server_requests', zone) ? latestPoint(request.points) : null,
      codes: {
        '2xx': codeValue(data.range.zoneStatusRate ?? [], zone, '2xx', 'nginx_vts_server_response_2xx_count'),
        '4xx': codeValue(data.range.zoneStatusRate ?? [], zone, '4xx', 'nginx_vts_server_response_4xx_count'),
        '5xx': codeValue(data.range.zoneStatusRate ?? [], zone, '5xx', 'nginx_vts_server_response_5xx_count'),
        '1xx': codeValue(data.range.zoneStatusRate ?? [], zone, '1xx', 'nginx_vts_server_response_1xx_count'),
        '3xx': codeValue(data.range.zoneStatusRate ?? [], zone, '3xx', 'nginx_vts_server_response_3xx_count')
      },
      bytesIn: byteValue(data.range.zoneBytes ?? [], zone, 'in', 'nginx_vts_server_in_bytes'),
      bytesOut: byteValue(data.range.zoneBytes ?? [], zone, 'out', 'nginx_vts_server_out_bytes'),
      timeMs: time?.fresh ? latestPoint(time.points) : null
    };
  }).sort((left, right) => sortNullLast(left.requestRate, right.requestRate) || sortNullLast(left.codes['5xx'], right.codes['5xx']));

  const summaryZone = '*';
  const summaryRequest = (data.range.starRequestRate ?? []).find((item) => labelOf(item.labels, 'zone') === '*' || !labelOf(item.labels, 'zone'));
  const summaryTime = starTime[0];
  const zoneSummary = (summaryRequest || summaryTime || (data.range.starStatusRate?.length ?? 0) > 0)
    ? {
      zone: summaryZone,
      requestRate: summaryRequest && zoneFresh('nginx_vts_server_requests', '*') ? latestPoint(summaryRequest.points) : null,
      codes: {
        '2xx': codeValue(data.range.starStatusRate ?? [], '*', '2xx', 'nginx_vts_server_response_2xx_count'),
        '4xx': codeValue(data.range.starStatusRate ?? [], '*', '4xx', 'nginx_vts_server_response_4xx_count'),
        '5xx': codeValue(data.range.starStatusRate ?? [], '*', '5xx', 'nginx_vts_server_response_5xx_count'),
        '1xx': codeValue(data.range.starStatusRate ?? [], '*', '1xx', 'nginx_vts_server_response_1xx_count'),
        '3xx': codeValue(data.range.starStatusRate ?? [], '*', '3xx', 'nginx_vts_server_response_3xx_count')
      },
      bytesIn: byteValue(data.range.starBytes ?? [], '*', 'in', 'nginx_vts_server_in_bytes'),
      bytesOut: byteValue(data.range.starBytes ?? [], '*', 'out', 'nginx_vts_server_out_bytes'),
      timeMs: summaryTime && starTimeFresh ? latestPoint(summaryTime.points) : null
    }
    : null;

  const memberKey = (labels: Record<string, string>) => (
    `${labelOf(labels, 'upstream')}|${labelOf(labels, 'upstream_address')}`
  );
  const memberFresh = (metric: string, upstreamName: string, address: string) => !namedFresh(
    upstreamFresh,
    nowSeconds,
    limit,
    metric,
    (labels) => labelOf(labels, 'upstream') === upstreamName && labelOf(labels, 'upstream_address') === address
  );
  const memberNames = new Map<string, { upstream: string; address: string }>();
  const rememberMember = (labels: Record<string, string>) => {
    const upstreamName = labelOf(labels, 'upstream');
    const address = labelOf(labels, 'upstream_address');
    if (!upstreamName && !address) return;
    memberNames.set(`${upstreamName}|${address}`, { upstream: upstreamName, address });
  };
  ['upRequestRate', 'upStatusRate', 'upBytes', 'upRequestTime', 'upResponseTime', 'upFlags'].forEach((key) => {
    (data.range[key] ?? []).forEach((item) => rememberMember(item.labels));
  });

  const members = Array.from(memberNames.values()).map((member) => {
    const request = (data.range.upRequestRate ?? []).find((item) => memberKey(item.labels) === `${member.upstream}|${member.address}`);
    const time = (data.range.upRequestTime ?? []).find((item) => memberKey(item.labels) === `${member.upstream}|${member.address}`);
    const response = (data.range.upResponseTime ?? []).find((item) => memberKey(item.labels) === `${member.upstream}|${member.address}`);
    const flag = (field: string) => {
      const found = (data.range.upFlags ?? []).find((item) => (
        memberKey(item.labels) === `${member.upstream}|${member.address}` && labelOf(item.labels, 'field') === field
      ));
      const metric = field === 'down'
        ? 'nginx_vts_upstream_down'
        : field === 'backup'
          ? 'nginx_vts_upstream_backup'
          : field === 'weight'
            ? 'nginx_vts_upstream_weight'
            : field === 'maxFails'
              ? 'nginx_vts_upstream_max_fails'
              : 'nginx_vts_upstream_fail_timeout';
      if (!found || !memberFresh(metric, member.upstream, member.address)) return null;
      return latestPoint(found.points);
    };
    const codeAt = (code: string) => {
      const found = (data.range.upStatusRate ?? []).find((item) => (
        memberKey(item.labels) === `${member.upstream}|${member.address}` && labelOf(item.labels, 'code') === code
      ));
      const metric = `nginx_vts_upstream_response_${code}_count`;
      if (!found || !memberFresh(metric, member.upstream, member.address)) return null;
      return latestPoint(found.points);
    };
    const bytesAt = (direction: string) => {
      const found = (data.range.upBytes ?? []).find((item) => (
        memberKey(item.labels) === `${member.upstream}|${member.address}` && labelOf(item.labels, 'direction') === direction
      ));
      const metric = direction === 'out' ? 'nginx_vts_upstream_out_bytes' : 'nginx_vts_upstream_in_bytes';
      if (!found || !memberFresh(metric, member.upstream, member.address)) return null;
      return latestPoint(found.points);
    };
    return {
      upstream: member.upstream,
      address: member.address,
      requestRate: request && memberFresh('nginx_vts_upstream_requests', member.upstream, member.address) ? latestPoint(request.points) : null,
      codes: { '4xx': codeAt('4xx'), '5xx': codeAt('5xx') },
      bytesIn: bytesAt('in'),
      bytesOut: bytesAt('out'),
      requestMs: time && memberFresh('nginx_vts_upstream_request_time', member.upstream, member.address) ? latestPoint(time.points) : null,
      responseMs: response && memberFresh('nginx_vts_upstream_response_time', member.upstream, member.address) ? latestPoint(response.points) : null,
      down: flag('down'),
      backup: flag('backup'),
      weight: flag('weight'),
      maxFails: flag('maxFails'),
      failTimeout: flag('failTimeout')
    } satisfies UpstreamMemberRow;
  });

  const groupNames = new Set<string>(members.map((member) => member.upstream).filter(Boolean));
  (data.range.upRequestSum ?? []).forEach((item) => {
    const name = labelOf(item.labels, 'upstream');
    if (name) groupNames.add(name);
  });
  const sumLatest = (series: readonly RangeSeries[], upstreamName: string, extra?: (labels: Record<string, string>) => boolean) => {
    const found = series.find((item) => labelOf(item.labels, 'upstream') === upstreamName && (extra ? extra(item.labels) : true));
    return found ? latestPoint(found.points) : null;
  };
  const groupStale = (upstreamName: string, metric: string) => {
    const samples = upstreamFresh.filter((sample) => (
      matchesMetric(sample.labels, metric) && labelOf(sample.labels, 'upstream') === upstreamName
    ));
    if (!samples.length) return true;
    return samples.some((sample) => isStale(mergeSourceTime([sample], nowSeconds), nowSeconds, limit));
  };
  const upstreamGroups = Array.from(groupNames).map((upstreamName) => ({
    upstream: upstreamName,
    requestRate: groupStale(upstreamName, 'nginx_vts_upstream_requests') ? null : sumLatest(data.range.upRequestSum ?? [], upstreamName),
    codes: {
      '4xx': groupStale(upstreamName, 'nginx_vts_upstream_response_4xx_count') ? null : sumLatest(data.range.upStatusSum ?? [], upstreamName, (labels) => labelOf(labels, 'code') === '4xx'),
      '5xx': groupStale(upstreamName, 'nginx_vts_upstream_response_5xx_count') ? null : sumLatest(data.range.upStatusSum ?? [], upstreamName, (labels) => labelOf(labels, 'code') === '5xx')
    },
    bytesIn: groupStale(upstreamName, 'nginx_vts_upstream_in_bytes') ? null : sumLatest(data.range.upBytesSum ?? [], upstreamName, (labels) => labelOf(labels, 'direction') === 'in'),
    bytesOut: groupStale(upstreamName, 'nginx_vts_upstream_out_bytes') ? null : sumLatest(data.range.upBytesSum ?? [], upstreamName, (labels) => labelOf(labels, 'direction') === 'out'),
    members: members
      .filter((member) => member.upstream === upstreamName)
      .sort((left, right) => sortNullLast(left.codes['5xx'], right.codes['5xx']) || sortNullLast(left.responseMs, right.responseMs))
  })).sort((left, right) => sortNullLast(left.codes['5xx'], right.codes['5xx']) || sortNullLast(left.requestRate, right.requestRate));

  const upstreamRequest = (data.range.upRequestRate ?? [])
    .filter((item) => labelOf(item.labels, 'code') === 'total' || labelOf(item.labels, 'code') === '')
    .map((item, index) => {
      const upstreamName = labelOf(item.labels, 'upstream');
      const address = labelOf(item.labels, 'upstream_address');
      const fresh = memberFresh('nginx_vts_upstream_requests', upstreamName, address);
      const value = fresh ? latestPoint(item.points) : null;
      const label = address ? `${upstreamName} ${address}` : upstreamName;
      return seriesItem(`${upstreamName}|${address}`, label, colorAt(index), item.points, value == null ? EMPTY_READING : formatPerSecond(value, '次'));
    });
  const upstreamStatus = sumByCode(data.range.upStatusRate ?? [])
    .sort((left, right) => statusOrder.indexOf(left.code) - statusOrder.indexOf(right.code))
    .map((item) => {
      const parts = (data.range.upStatusRate ?? []).filter((series) => labelOf(series.labels, 'code') === item.code);
      const stale = parts.some((series) => !memberFresh(
        `nginx_vts_upstream_response_${item.code}_count`,
        labelOf(series.labels, 'upstream'),
        labelOf(series.labels, 'upstream_address')
      ));
      const value = stale ? null : latestPoint(item.points);
      return seriesItem(
        item.code,
        item.code,
        CODE_COLORS[item.code] || colorAt(0),
        item.points,
        value == null ? EMPTY_READING : formatPerSecond(value, '次')
      );
    });
  const upstreamTimeRows = (key: 'upRequestTime' | 'upResponseTime', metric: string) => (
    (data.range[key] ?? []).map((item) => {
      const upstreamName = labelOf(item.labels, 'upstream');
      const address = labelOf(item.labels, 'upstream_address');
      return {
        id: `${upstreamName}|${address}`,
        label: address ? `${upstreamName} ${address}` : upstreamName,
        points: item.points,
        fresh: memberFresh(metric, upstreamName, address)
      };
    })
  );
  const requestTimeRows = upstreamTimeRows('upRequestTime', 'nginx_vts_upstream_request_time');
  const responseTimeRows = upstreamTimeRows('upResponseTime', 'nginx_vts_upstream_response_time');
  const upstreamPeak = [...requestTimeRows, ...responseTimeRows].reduce((peak, item) => (
    Math.max(peak, ...item.points.map((point) => Math.abs(point.value)))
  ), 0);
  const upstreamTimeUnit = pickDurationUnit(upstreamPeak);
  const upstreamRequestTime = durationItems(requestTimeRows, upstreamTimeUnit);
  const upstreamResponseTime = durationItems(responseTimeRows, upstreamTimeUnit);
  const upstreamDownOnly = members.some((member) => member.down === 1);

  const filterNames = new Map<string, { filterName: string; filterKey: string }>();
  const rememberFilter = (labels: Record<string, string>) => {
    const filterName = labelOf(labels, 'filter_name');
    const filterKey = labelOf(labels, 'filter_key');
    if (!filterName && !filterKey) return;
    filterNames.set(`${filterName}|${filterKey}`, { filterName, filterKey });
  };
  ['filterRequestRate', 'filterStatusRate', 'filterBytes', 'filterTime'].forEach((key) => {
    (data.range[key] ?? []).forEach((item) => rememberFilter(item.labels));
  });
  const filterFreshEnough = (metric: string, filterName: string, filterKey: string) => !namedFresh(
    data.instant.filterFresh ?? [],
    nowSeconds,
    limit,
    metric,
    (labels) => labelOf(labels, 'filter_name') === filterName && labelOf(labels, 'filter_key') === filterKey
  );
  const filterRows = Array.from(filterNames.values()).map((filter) => {
    const id = `${filter.filterName}|${filter.filterKey}`;
    const request = (data.range.filterRequestRate ?? []).find((item) => `${labelOf(item.labels, 'filter_name')}|${labelOf(item.labels, 'filter_key')}` === id);
    const time = (data.range.filterTime ?? []).find((item) => `${labelOf(item.labels, 'filter_name')}|${labelOf(item.labels, 'filter_key')}` === id);
    const codeAt = (code: string) => {
      const found = (data.range.filterStatusRate ?? []).find((item) => (
        `${labelOf(item.labels, 'filter_name')}|${labelOf(item.labels, 'filter_key')}` === id && labelOf(item.labels, 'code') === code
      ));
      if (!found || !filterFreshEnough(`nginx_vts_filter_response_${code}_count`, filter.filterName, filter.filterKey)) return null;
      return latestPoint(found.points);
    };
    const bytesAt = (direction: string) => {
      const found = (data.range.filterBytes ?? []).find((item) => (
        `${labelOf(item.labels, 'filter_name')}|${labelOf(item.labels, 'filter_key')}` === id && labelOf(item.labels, 'direction') === direction
      ));
      const metric = direction === 'out' ? 'nginx_vts_filter_out_bytes' : 'nginx_vts_filter_in_bytes';
      if (!found || !filterFreshEnough(metric, filter.filterName, filter.filterKey)) return null;
      return latestPoint(found.points);
    };
    return {
      filterName: filter.filterName,
      filterKey: filter.filterKey,
      requestRate: request && filterFreshEnough('nginx_vts_filter_requests', filter.filterName, filter.filterKey) ? latestPoint(request.points) : null,
      codes: {
        '1xx': codeAt('1xx'),
        '2xx': codeAt('2xx'),
        '3xx': codeAt('3xx'),
        '4xx': codeAt('4xx'),
        '5xx': codeAt('5xx')
      },
      bytesIn: bytesAt('in'),
      bytesOut: bytesAt('out'),
      timeMs: time && filterFreshEnough('nginx_vts_filter_request_time', filter.filterName, filter.filterKey) ? latestPoint(time.points) : null
    };
  }).sort((left, right) => sortNullLast(left.requestRate, right.requestRate));
  const filterRequest = (data.range.filterRequestRate ?? []).map((item, index) => {
    const filterName = labelOf(item.labels, 'filter_name');
    const filterKey = labelOf(item.labels, 'filter_key');
    const fresh = filterFreshEnough('nginx_vts_filter_requests', filterName, filterKey);
    const value = fresh ? latestPoint(item.points) : null;
    const label = filterKey ? `${filterName} ${filterKey}` : filterName;
    return seriesItem(`${filterName}|${filterKey}`, label, colorAt(index), item.points, value == null ? EMPTY_READING : formatPerSecond(value, '次'));
  });

  const has5xx = zoneRows.some((row) => (row.codes['5xx'] ?? 0) > 0) || (zoneSummary?.codes['5xx'] ?? 0) > 0;
  const shape = requestShape(requestPoints, requestStale);
  const requestDetail = shape === 'up' ? '窗口后段明显高于前段' : shape === 'down' ? '窗口后段明显低于前段' : shape === 'steady' ? '窗口内变化不大' : '当前窗口没有可比的速率';
  let fourthTitle = '等待连接占比';
  let fourthValue = formatPercent(waitingShare);
  let fourthDetail = '空闲等待占活跃连接的比例';
  let fourthTab: 'sites' | 'upstream' | 'connections' = 'connections';
  if (upstream && upstreamDownOnly) {
    fourthTitle = '站点/上游异常';
    fourthValue = '有后端下线';
    fourthDetail = '上游成员被标记为下线';
    fourthTab = 'upstream';
  } else if (sites && has5xx) {
    fourthTitle = '站点/上游异常';
    fourthValue = '有 5xx';
    fourthDetail = '站点响应里出现 5xx';
    fourthTab = 'sites';
  }

  return {
    collection: {
      kind,
      label: collectionLabel,
      tone: kind === 'success' ? 'var(--color-success)' : undefined
    },
    request: requestNow == null ? EMPTY_READING : formatPerSecond(requestNow, '次'),
    accepts: acceptNow == null ? EMPTY_READING : formatPerSecond(acceptNow, '连接'),
    handledRate: handledNow == null ? EMPTY_READING : formatPerSecond(handledNow, '连接'),
    active: activeNow == null ? EMPTY_READING : formatCount(activeNow, '个'),
    dropped: droppedNow == null ? EMPTY_READING : formatPerSecond(droppedNow, '连接'),
    handled: formatPercent(handledShare),
    busy: formatPercent(busyNow),
    waiting: formatPercent(waitingShare),
    alertReady: true,
    requestPoints,
    acceptPoints,
    handledPoints,
    droppedPoints,
    connSeries,
    busyPoints,
    waitingPoints: waitingRatioPoints,
    ring: {
      active: activeNow,
      reading: readingNow,
      writing: writingNow,
      waiting: waitingNow
    },
    requestTotal: totalNow == null ? null : formatCount(totalNow, '次'),
    showRequestTime,
    requestTime: showRequestTime && starTimeFresh ? formatDuration(latestPoint(starTimePoints) ?? Number.NaN, requestTimeUnit) : EMPTY_READING,
    requestTimePoints: starTimePoints,
    requestTimeUnit,
    focus: {
      requestValue: requestNow == null ? EMPTY_READING : formatPerSecond(requestNow, '次'),
      requestDetail,
      requestTab: sites ? 'sites' : null,
      connectionValue: busyNow == null ? EMPTY_READING : formatPercent(busyNow),
      connectionDetail: waitingShare == null ? '等待占比暂无数据' : `等待占比 ${formatPercent(waitingShare)}`,
      dropValue: droppedNow == null ? EMPTY_READING : formatPerSecond(droppedNow, '连接'),
      dropDetail: handledShare == null ? '完成率暂无数据' : `完成率 ${formatPercent(handledShare)}`,
      fourthTitle,
      fourthValue,
      fourthDetail,
      fourthTab
    },
    tabs: { sites, upstream },
    showFilter,
    zoneRequest,
    zoneStatus,
    zoneBytes,
    zoneTime,
    zoneTimeUnit,
    byteScaleDiv: scale.div,
    byteSuffix: scale.suffix,
    zoneRows,
    zoneSummary,
    upstreamRequest,
    upstreamStatus,
    upstreamRequestTime,
    upstreamResponseTime,
    upstreamTimeUnit,
    upstreamGroups,
    upstreamDownOnly,
    filterRequest,
    filterRows
  };
};

export const zoneColumns = (rows: readonly ZoneTableRow[]) => {
  const all = [...rows];
  const show = (pick: (row: ZoneTableRow) => number | null) => all.some((row) => hasFinite(pick(row)));
  return {
    request: show((row) => row.requestRate),
    c2: show((row) => row.codes['2xx']),
    c4: show((row) => row.codes['4xx']),
    c5: show((row) => row.codes['5xx']),
    c1: show((row) => row.codes['1xx']),
    c3: show((row) => row.codes['3xx']),
    bytesIn: show((row) => row.bytesIn),
    bytesOut: show((row) => row.bytesOut),
    time: show((row) => row.timeMs)
  };
};

export const upstreamColumns = (groups: readonly UpstreamGroupRow[]) => {
  const members = groups.flatMap((group) => group.members);
  const showMember = (pick: (row: UpstreamMemberRow) => number | null) => (
    members.some((row) => hasFinite(pick(row)))
  );
  return {
    request: showMember((row) => row.requestRate) || groups.some((group) => hasFinite(group.requestRate)),
    c4: showMember((row) => row.codes['4xx']) || groups.some((group) => hasFinite(group.codes['4xx'])),
    c5: showMember((row) => row.codes['5xx']) || groups.some((group) => hasFinite(group.codes['5xx'])),
    bytesIn: showMember((row) => row.bytesIn) || groups.some((group) => hasFinite(group.bytesIn)),
    bytesOut: showMember((row) => row.bytesOut) || groups.some((group) => hasFinite(group.bytesOut)),
    requestMs: showMember((row) => row.requestMs),
    responseMs: showMember((row) => row.responseMs),
    down: showMember((row) => row.down),
    backup: showMember((row) => row.backup),
    weight: showMember((row) => row.weight),
    maxFails: showMember((row) => row.maxFails),
    failTimeout: showMember((row) => row.failTimeout)
  };
};
