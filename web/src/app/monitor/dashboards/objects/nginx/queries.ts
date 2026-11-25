/**
 * Nginx 专业盘查询。打在 TSDB 原始名上，窗口跟盘面走。
 * 传统盘 config.ts 里的查询保持原样，不在这里改。
 */

const CODES = ['1xx', '2xx', '3xx', '4xx', '5xx'] as const;

const statusRate = (prefix: string, selector: string, codes: readonly string[] = CODES) => (
  codes.map((code) => (
    `label_replace(rate(${prefix}_response_${code}_count${selector}[__$window__]), "code", "${code}", "__name__", ".*")`
  )).join(' or ')
);

const bytesRate = (prefix: string, selector: string) => (
  `label_replace(rate(${prefix}_in_bytes${selector}[__$window__]), "direction", "in", "__name__", ".*") or label_replace(rate(${prefix}_out_bytes${selector}[__$window__]), "direction", "out", "__name__", ".*")`
);

const totalRate = (metric: string, selector: string) => (
  `label_replace(rate(${metric}${selector}[__$window__]), "code", "total", "__name__", ".*")`
);

/** `or` 忽略 __name__，同标签会只留下左边一条。补上互斥的 metric 后每条原始序列都还在。 */
const tlastOr = (metrics: readonly string[]) => (
  metrics.map((metric) => (
    `label_replace(tlast_over_time(${metric}{__$labels__}[20m]), "metric", "${metric}", "__name__", ".+")`
  )).join(' or ')
);

const presentOr = (metrics: readonly string[]) => (
  metrics.map((metric) => `last_over_time(${metric}{__$labels__}[24h])`).join(' or ')
);

const ZONE_DETAIL = '{__$labels__,zone!="*"}';
const ZONE_STAR = '{__$labels__,zone="*"}';
const ANY = '{__$labels__}';

const SERVER_RAW = [
  'nginx_vts_server_requests',
  'nginx_vts_server_in_bytes',
  'nginx_vts_server_out_bytes',
  'nginx_vts_server_request_time',
  'nginx_vts_server_response_1xx_count',
  'nginx_vts_server_response_2xx_count',
  'nginx_vts_server_response_3xx_count',
  'nginx_vts_server_response_4xx_count',
  'nginx_vts_server_response_5xx_count'
] as const;

const UPSTREAM_RAW = [
  'nginx_vts_upstream_requests',
  'nginx_vts_upstream_in_bytes',
  'nginx_vts_upstream_out_bytes',
  'nginx_vts_upstream_request_time',
  'nginx_vts_upstream_response_time',
  'nginx_vts_upstream_response_1xx_count',
  'nginx_vts_upstream_response_2xx_count',
  'nginx_vts_upstream_response_3xx_count',
  'nginx_vts_upstream_response_4xx_count',
  'nginx_vts_upstream_response_5xx_count',
  'nginx_vts_upstream_down',
  'nginx_vts_upstream_backup',
  'nginx_vts_upstream_weight',
  'nginx_vts_upstream_max_fails',
  'nginx_vts_upstream_fail_timeout'
] as const;

const FILTER_RAW = [
  'nginx_vts_filter_requests',
  'nginx_vts_filter_in_bytes',
  'nginx_vts_filter_out_bytes',
  'nginx_vts_filter_request_time',
  'nginx_vts_filter_response_1xx_count',
  'nginx_vts_filter_response_2xx_count',
  'nginx_vts_filter_response_3xx_count',
  'nginx_vts_filter_response_4xx_count',
  'nginx_vts_filter_response_5xx_count'
] as const;

const STUB_FRESH = [
  'nginx_active',
  'nginx_reading',
  'nginx_writing',
  'nginx_waiting',
  'nginx_requests',
  'nginx_accepts',
  'nginx_handled'
] as const;

export interface NginxQuerySpec {
  key: string;
  query: string;
  instant: boolean;
}

const range = (key: string, query: string): NginxQuerySpec => ({ key, query, instant: false });
const instant = (key: string, query: string): NginxQuerySpec => ({ key, query, instant: true });

export const NGINX_PRO_QUERIES: readonly NginxQuerySpec[] = [
  range('conn', [
    ['active', 'nginx_active'],
    ['reading', 'nginx_reading'],
    ['writing', 'nginx_writing'],
    ['waiting', 'nginx_waiting']
  ].map(([status, metric]) => (
    `label_replace(${metric}{__$labels__}, "status", "${status}", "__name__", ".*")`
  )).join(' or ')),
  range('requestsRate', 'rate(nginx_requests{__$labels__}[__$window__])'),
  range('acceptsRate', 'rate(nginx_accepts{__$labels__}[__$window__])'),
  range('handledRate', 'rate(nginx_handled{__$labels__}[__$window__])'),
  range('requestsTotal', 'nginx_requests{__$labels__}'),
  instant('stubFresh', tlastOr(STUB_FRESH)),
  instant('serverFresh', tlastOr(SERVER_RAW)),
  instant('upstreamFresh', tlastOr(UPSTREAM_RAW)),
  instant('filterFresh', tlastOr(FILTER_RAW)),
  instant('serverCap', presentOr(SERVER_RAW)),
  instant('upstreamCap', presentOr(UPSTREAM_RAW)),
  instant('filterCap', presentOr(FILTER_RAW)),
  range('zoneRequestRate', totalRate('nginx_vts_server_requests', ZONE_DETAIL)),
  range('starRequestRate', totalRate('nginx_vts_server_requests', ZONE_STAR)),
  range('zoneStatusRate', statusRate('nginx_vts_server', ZONE_DETAIL)),
  range('starStatusRate', statusRate('nginx_vts_server', ZONE_STAR)),
  range('zoneBytes', bytesRate('nginx_vts_server', ZONE_DETAIL)),
  range('starBytes', bytesRate('nginx_vts_server', ZONE_STAR)),
  range('zoneTime', `nginx_vts_server_request_time${ZONE_DETAIL}`),
  range('starTime', `nginx_vts_server_request_time${ZONE_STAR}`),
  range('upRequestRate', totalRate('nginx_vts_upstream_requests', ANY)),
  range('upRequestSum', `sum by (upstream) (${totalRate('nginx_vts_upstream_requests', ANY)})`),
  range('upStatusRate', statusRate('nginx_vts_upstream', ANY)),
  range('upStatusSum', `sum by (upstream, code) (${statusRate('nginx_vts_upstream', ANY, ['4xx', '5xx'])})`),
  range('upBytes', bytesRate('nginx_vts_upstream', ANY)),
  range('upBytesSum', `sum by (upstream, direction) (${bytesRate('nginx_vts_upstream', ANY)})`),
  range('upRequestTime', `nginx_vts_upstream_request_time${ANY}`),
  range('upResponseTime', `nginx_vts_upstream_response_time${ANY}`),
  range('upFlags', [
    ['down', 'nginx_vts_upstream_down'],
    ['backup', 'nginx_vts_upstream_backup'],
    ['weight', 'nginx_vts_upstream_weight'],
    ['maxFails', 'nginx_vts_upstream_max_fails'],
    ['failTimeout', 'nginx_vts_upstream_fail_timeout']
  ].map(([field, metric]) => (
    `label_replace(${metric}{__$labels__}, "field", "${field}", "__name__", ".*")`
  )).join(' or ')),
  range('filterRequestRate', totalRate('nginx_vts_filter_requests', ANY)),
  range('filterStatusRate', statusRate('nginx_vts_filter', ANY)),
  range('filterBytes', bytesRate('nginx_vts_filter', ANY)),
  range('filterTime', `nginx_vts_filter_request_time${ANY}`)
];

export const nginxQueryByKey = (key: string) => (
  NGINX_PRO_QUERIES.find((item) => item.key === key)?.query ?? ''
);
