/**
 * 网络流量仪表盘本地 Mock。
 * 仅在 NEXT_PUBLIC_LOG_ANALYSIS_MOCK=true 时由 WidgetWrapper 注入，
 * 用于本地无 VictoriaLogs 数据时预览 flows / http 组件。
 */

const BUCKET_COUNT = 12;

export const isLogAnalysisMockEnabled = () =>
  process.env.NODE_ENV === 'development' &&
  process.env.NEXT_PUBLIC_LOG_ANALYSIS_MOCK === 'true';

const toIso = (ms: number) => new Date(ms).toISOString();

const buildTimeBuckets = (times?: number[]) => {
  const end = times?.[1] || Date.now();
  const start = times?.[0] || end - 15 * 60 * 1000;
  const step = Math.max(Math.floor((end - start) / BUCKET_COUNT), 60_000);
  const buckets: string[] = [];
  for (let t = start + step; t <= end; t += step) {
    buckets.push(toIso(t));
  }
  if (!buckets.length) {
    buckets.push(toIso(end));
  }
  return buckets;
};

const wave = (index: number, base: number, amplitude: number) =>
  Math.max(
    0,
    Math.round(base + amplitude * Math.sin((index / BUCKET_COUNT) * Math.PI * 2))
  );

const timeSeries = (
  times: number[] | undefined,
  field: string,
  base: number,
  amplitude: number
) =>
  buildTimeBuckets(times).map((time, index) => ({
    _time: time,
    [field]: wave(index, base, amplitude)
  }));

const multiFieldTimeSeries = (
  times: number[] | undefined,
  fields: Record<string, { base: number; amplitude: number }>
) =>
  buildTimeBuckets(times).map((time, index) => {
    const row: Record<string, unknown> = { _time: time };
    Object.entries(fields).forEach(([field, { base, amplitude }]) => {
      row[field] = wave(index, base, amplitude);
    });
    return row;
  });

const buildFlowKpiMock = (config: any, times?: number[]) => {
  const valueField =
    config?.displayMaps?.value ||
    config?.valueField ||
    Object.keys(config?.displayMaps || {}).find((key) => key !== 'type') ||
    'value';
  const known: Record<string, { base: number; amplitude: number }> = {
    networkbytes: { base: 180, amplitude: 40 },
    networkpackets: { base: 320000, amplitude: 40000 },
    flowcount: { base: 1400, amplitude: 200 },
    long_flows: { base: 10, amplitude: 3 }
  };
  const profile = known[valueField] || { base: 100, amplitude: 20 };
  return timeSeries(times, valueField, profile.base, profile.amplitude);
};

const buildHttpKpiMock = (config: any, times?: number[]) => {
  const calculation = config?.calculation || 'sum';
  const buckets = buildTimeBuckets(times);

  if (calculation === 'ratio') {
    return buckets.map((time, index) => ({
      _time: time,
      total_count: wave(index, 7000, 800),
      success_count: wave(index, 6800, 700),
      error_count: wave(index, 180, 40)
    }));
  }

  if (calculation === 'weightedAverage') {
    const valueField = config?.valueField || 'avg_duration';
    const weightField = config?.weightField || 'reqcount';
    if (config?.dataSourceParams?.queries?.length) {
      return {
        count: buckets.map((time, index) => ({
          _time: time,
          [weightField]: wave(index, 7000, 800)
        })),
        p95: buckets.map((time, index) => ({
          _time: time,
          [valueField]: wave(index, 160, 40)
        }))
      };
    }
    return buckets.map((time, index) => ({
      _time: time,
      [weightField]: wave(index, 7000, 800),
      [valueField]: wave(index, 60, 12)
    }));
  }

  const valueField = config?.valueField || 'reqcount';
  const known: Record<string, { base: number; amplitude: number }> = {
    reqcount: { base: 7200, amplitude: 900 },
    total_traffic_mb: { base: 36, amplitude: 8 }
  };
  const profile = known[valueField] || { base: 100, amplitude: 20 };
  return timeSeries(times, valueField, profile.base, profile.amplitude);
};

const buildFlowTrendMock = (times?: number[]) => {
  const transports = ['tcp', 'udp', 'icmp'] as const;
  const profiles = {
    tcp: { base: 220, amplitude: 45 },
    udp: { base: 42, amplitude: 10 },
    icmp: { base: 3, amplitude: 1 }
  };
  const rows: Record<string, unknown>[] = [];
  buildTimeBuckets(times).forEach((time, index) => {
    transports.forEach((transport) => {
      rows.push({
        _time: time,
        'network.transport': transport,
        networkbytes: wave(
          index,
          profiles[transport].base,
          profiles[transport].amplitude
        )
      });
    });
  });
  return rows;
};

const buildHttpRequestTableMock = (config: any) => {
  const queries = config?.dataSourceParams?.queries || [];
  const keys = queries.map((item: { key: string }) => item.key);

  if (keys.includes('detail') && keys.includes('total')) {
    return {
      detail: [
        {
          'url.path': '/api/orders',
          reqcount: 12400,
          avg_duration: 88,
          p95_duration: 210
        },
        {
          'url.path': '/api/login',
          reqcount: 8100,
          avg_duration: 42,
          p95_duration: 92
        },
        {
          'url.path': '/health',
          reqcount: 7600,
          avg_duration: 4,
          p95_duration: 8
        },
        {
          'url.path': '/api/cart',
          reqcount: 4200,
          avg_duration: 76,
          p95_duration: 164
        },
        {
          'url.path': '/api/search',
          reqcount: 3100,
          avg_duration: 180,
          p95_duration: 420
        }
      ],
      total: [{ total_reqcount: 86420 }]
    };
  }

  if (keys.includes('base') && keys.includes('p95')) {
    return {
      base: [
        { 'url.path': '/api/report', reqcount: 640, avg_duration: 920 },
        { 'url.path': '/api/export', reqcount: 210, avg_duration: 760 },
        { 'url.path': '/api/search', reqcount: 3100, avg_duration: 180 },
        { 'url.path': '/api/orders', reqcount: 12400, avg_duration: 88 }
      ],
      p95: [
        { 'url.path': '/api/report', p95_duration: 1800 },
        { 'url.path': '/api/export', p95_duration: 1200 },
        { 'url.path': '/api/search', p95_duration: 420 },
        { 'url.path': '/api/orders', p95_duration: 210 }
      ]
    };
  }

  if (keys.includes('errors') && keys.includes('status')) {
    return {
      errors: [
        {
          'url.path': '/api/pay',
          reqcount: 880,
          error_count: 160,
          error_rate: 18.2
        },
        {
          'url.path': '/api/login',
          reqcount: 8100,
          error_count: 332,
          error_rate: 4.1
        },
        {
          'url.path': '/api/orders',
          reqcount: 12400,
          error_count: 198,
          error_rate: 1.6
        }
      ],
      status: [
        {
          'url.path': '/api/pay',
          'http.response.status_code': 502,
          status_count: 120
        },
        {
          'url.path': '/api/login',
          'http.response.status_code': 401,
          status_count: 280
        },
        {
          'url.path': '/api/orders',
          'http.response.status_code': 500,
          status_count: 140
        }
      ]
    };
  }

  return [
    { 'url.path': '/api/orders', reqcount: 12400, avg_duration: 88 }
  ];
};

/** 按图表类型生成与真实 LogSQL 结果同形的 Mock。 */
export const buildNetworkDashboardMock = (
  chartType: string | undefined,
  config: any,
  times?: number[]
) => {
  switch (chartType) {
    case 'flowKpiCard':
      return buildFlowKpiMock(config, times);
    case 'httpKpiCard':
      return buildHttpKpiMock(config, times);
    case 'flowTrend':
      return buildFlowTrendMock(times);
    case 'flowDonut':
      return [
        { 'network.transport': 'tcp', flowcount: 15120 },
        { 'network.transport': 'udp', flowcount: 2948 },
        { 'network.transport': 'icmp', flowcount: 362 }
      ];
    case 'flowBar': {
      const key = config?.displayMaps?.key;
      if (key === 'destination.port') {
        return [
          { 'destination.port': 443, dst_bytes: 610 },
          { 'destination.port': 80, dst_bytes: 240 },
          { 'destination.port': 8080, dst_bytes: 180 },
          { 'destination.port': 22, dst_bytes: 96 },
          { 'destination.port': 3306, dst_bytes: 72 }
        ];
      }
      return [
        { 'source.ip': '10.0.12.18', src_bytes: 420 },
        { 'source.ip': '10.0.12.24', src_bytes: 310 },
        { 'source.ip': '192.168.8.7', src_bytes: 186 },
        { 'source.ip': '10.0.4.11', src_bytes: 142 },
        { 'source.ip': '172.16.1.9', src_bytes: 98 }
      ];
    }
    case 'flowSankey':
      return [
        {
          'source.ip': '10.0.12.18',
          'destination.ip': '203.0.113.10',
          'network.transport': 'tcp',
          'source.port': 51234,
          'destination.port': 443,
          flow_bytes: 186
        },
        {
          'source.ip': '10.0.12.24',
          'destination.ip': '203.0.113.12',
          'network.transport': 'tcp',
          'source.port': 49821,
          'destination.port': 443,
          flow_bytes: 154
        },
        {
          'source.ip': '192.168.8.7',
          'destination.ip': '10.0.4.30',
          'network.transport': 'tcp',
          'source.port': 40112,
          'destination.port': 8080,
          flow_bytes: 96
        },
        {
          'source.ip': '10.0.4.11',
          'destination.ip': '8.8.8.8',
          'network.transport': 'udp',
          'source.port': 53122,
          'destination.port': 53,
          flow_bytes: 22
        },
        {
          'source.ip': '172.16.1.9',
          'destination.ip': '10.0.12.1',
          'network.transport': 'tcp',
          'source.port': 39001,
          'destination.port': 22,
          flow_bytes: 18
        }
      ];
    case 'flowTable':
      return [
        {
          'source.ip': '10.0.12.18',
          'destination.ip': '203.0.113.10',
          'network.transport': 'tcp',
          'destination.port': 443,
          flow_bytes: 186,
          duration_sec: 142
        },
        {
          'source.ip': '10.0.12.24',
          'destination.ip': '203.0.113.12',
          'network.transport': 'tcp',
          'destination.port': 443,
          flow_bytes: 154,
          duration_sec: 88
        },
        {
          'source.ip': '192.168.8.7',
          'destination.ip': '10.0.4.30',
          'network.transport': 'tcp',
          'destination.port': 8080,
          flow_bytes: 96,
          duration_sec: 41
        },
        {
          'source.ip': '10.0.4.11',
          'destination.ip': '8.8.8.8',
          'network.transport': 'udp',
          'destination.port': 53,
          flow_bytes: 22,
          duration_sec: 12
        },
        {
          'source.ip': '172.16.1.9',
          'destination.ip': '10.0.12.1',
          'network.transport': 'tcp',
          'destination.port': 22,
          flow_bytes: 18,
          duration_sec: 610
        }
      ];
    case 'httpRequestTrend':
      return multiFieldTimeSeries(times, {
        reqcount: { base: 17000, amplitude: 2200 },
        avg_duration: { base: 64, amplitude: 10 },
        p95_duration: { base: 180, amplitude: 30 }
      });
    case 'httpStatusCategoryDonut':
      return [
        { 'http.response.status_code': 200, reqcount: 78000 },
        { 'http.response.status_code': 201, reqcount: 4100 },
        { 'http.response.status_code': 301, reqcount: 1200 },
        { 'http.response.status_code': 401, reqcount: 980 },
        { 'http.response.status_code': 404, reqcount: 820 },
        { 'http.response.status_code': 500, reqcount: 260 },
        { 'http.response.status_code': 502, reqcount: 160 }
      ];
    case 'httpRequestTable':
      return buildHttpRequestTableMock(config);
    case 'httpDonut':
      return [
        { 'http.request.method': 'GET', reqcount: 61200 },
        { 'http.request.method': 'POST', reqcount: 19800 },
        { 'http.request.method': 'PUT', reqcount: 3400 },
        { 'http.request.method': 'DELETE', reqcount: 1020 }
      ];
    case 'httpLatencyBar':
      return [
        {
          bucket_lt50: 42000,
          bucket_50_100: 21000,
          bucket_100_200: 12000,
          bucket_200_500: 6800,
          bucket_500_1000: 2400,
          bucket_1000_2000: 980,
          bucket_2000_5000: 420,
          bucket_gt5000: 120
        }
      ];
    case 'httpStatusTrend': {
      const codes = [200, 301, 401, 500] as const;
      const rows: Record<string, unknown>[] = [];
      buildTimeBuckets(times).forEach((time, index) => {
        codes.forEach((code) => {
          const base =
            code === 200 ? 6200 : code === 301 ? 180 : code === 401 ? 90 : 40;
          rows.push({
            _time: time,
            'http.response.status_code': code,
            reqcount: wave(index, base, Math.max(8, Math.round(base * 0.12)))
          });
        });
      });
      return rows;
    }
    case 'httpBarLine':
      return multiFieldTimeSeries(times, {
        reqcount: { base: 17000, amplitude: 2200 },
        avg_duration: { base: 64, amplitude: 10 }
      });
    default:
      return [];
  }
};

export const isNetworkDashboardChartType = (chartType?: string) =>
  !!chartType &&
  /^(flow|http)/.test(chartType);
