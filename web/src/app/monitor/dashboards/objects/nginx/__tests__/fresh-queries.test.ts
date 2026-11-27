import { describe, expect, it } from 'vitest';

import { NGINX_PRO_QUERIES } from '../queries';

const FRESH_METRICS = {
  stubFresh: [
    'nginx_active',
    'nginx_reading',
    'nginx_writing',
    'nginx_waiting',
    'nginx_requests',
    'nginx_accepts',
    'nginx_handled'
  ],
  serverFresh: [
    'nginx_vts_server_requests',
    'nginx_vts_server_in_bytes',
    'nginx_vts_server_out_bytes',
    'nginx_vts_server_request_time',
    'nginx_vts_server_response_1xx_count',
    'nginx_vts_server_response_2xx_count',
    'nginx_vts_server_response_3xx_count',
    'nginx_vts_server_response_4xx_count',
    'nginx_vts_server_response_5xx_count'
  ],
  upstreamFresh: [
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
  ],
  filterFresh: [
    'nginx_vts_filter_requests',
    'nginx_vts_filter_in_bytes',
    'nginx_vts_filter_out_bytes',
    'nginx_vts_filter_request_time',
    'nginx_vts_filter_response_1xx_count',
    'nginx_vts_filter_response_2xx_count',
    'nginx_vts_filter_response_3xx_count',
    'nginx_vts_filter_response_4xx_count',
    'nginx_vts_filter_response_5xx_count'
  ]
} as const;

const freshBranch = (metric: string) => (
  `label_replace(tlast_over_time(${metric}{__$labels__}[20m]), "metric", "${metric}", "", ".*")`
);

const outerNameReplace = /label_replace\(\s*tlast_over_time\([\s\S]*?\)\s*,[\s\S]*?"__name__"/;

describe('nginx freshness queries', () => {
  it.each(Object.keys(FRESH_METRICS))('%s labels each tlast branch without __name__', (key) => {
    const spec = NGINX_PRO_QUERIES.find((item) => item.key === key);
    const metrics = FRESH_METRICS[key as keyof typeof FRESH_METRICS];
    expect(spec?.instant).toBe(true);
    const query = spec?.query ?? '';
    const branches = query.split(' or ');
    expect(branches).toEqual(metrics.map(freshBranch));
    expect(query).not.toMatch(outerNameReplace);
    expect(query).not.toContain('__name__');
    expect(query).not.toContain('".+"');
    const metricLabels = branches.map((branch) => branch.match(/"metric", "([^"]+)"/)?.[1]);
    expect(metricLabels).toEqual([...metrics]);
    expect(new Set(metricLabels).size).toBe(metrics.length);
  });
});
