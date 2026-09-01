import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';
import { telegrafHistogramQuantile } from '../../shared/utils/telegrafHistogram';

const histQuantile = (base: string, quantile: string) => telegrafHistogramQuantile(base, quantile);

export const SGLANG_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'sglang',
  pageTitle: 'SGLang 监控仪表盘',
  objectFallbackName: 'SGLang',
  instanceType: 'sglang',
  collectionStatusQuery:
    "count({instance_type='sglang', collect_type='bkpull', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'bkpull', 'Prometheus'],
  metrics: [
    {
      name: 'sglang_running_reqs',
      display_name: '运行中请求数',
      description: '当前正在处理的请求数量。',
      unit: 'counts',
      query: "sum(sglang:num_running_reqs_gauge{__$labels__})",
      color: '#2f6bff'
    },
    {
      name: 'sglang_queue_reqs',
      display_name: '排队请求数',
      description: '当前等待队列中的请求数量。',
      unit: 'counts',
      query: "sum(sglang:num_queue_reqs_gauge{__$labels__})",
      color: '#faad14'
    },
    {
      name: 'sglang_token_usage',
      display_name: 'Token 用量',
      description: 'KV/token 用量比例（0–100%）。',
      unit: 'percent',
      query: "clamp_max(100 * avg(sglang:token_usage_gauge{__$labels__}), 100)",
      color: '#ff8a1f'
    },
    {
      name: 'sglang_cache_hit_rate',
      display_name: '缓存命中率',
      description: 'Prefix cache 命中率（0–100%）。',
      unit: 'percent',
      query: "clamp_max(100 * avg(sglang:cache_hit_rate_gauge{__$labels__}), 100)",
      color: '#27c274'
    },
    {
      name: 'sglang_prompt_tokens_rate',
      display_name: 'Prefill Token 速率',
      description: '最近 5 分钟 prefill token 处理速率。',
      unit: 'cps',
      query: "sum(rate(sglang:prompt_tokens_total_counter{__$labels__}[5m]))",
      color: '#13c2c2'
    },
    {
      name: 'sglang_generation_tokens_rate',
      display_name: '生成 Token 速率',
      description: '最近 5 分钟生成 token 速率。',
      unit: 'cps',
      query: "sum(rate(sglang:generation_tokens_total_counter{__$labels__}[5m]))",
      color: '#27c274'
    },
    {
      name: 'sglang_gen_throughput',
      display_name: '生成吞吐',
      description: '当前生成吞吐（token/s）。',
      unit: 'cps',
      query: "sum(sglang:gen_throughput_gauge{__$labels__})",
      color: '#597ef7'
    },
    {
      name: 'sglang_ttft_p99',
      display_name: '首 Token 时延 P99',
      description: '最近 5 分钟 TTFT P99。',
      unit: 's',
      query:
        histQuantile('sglang:time_to_first_token_seconds', '0.99'),
      color: '#597ef7'
    },
    {
      name: 'sglang_e2e_p99',
      display_name: '端到端时延 P99',
      description: '最近 5 分钟端到端请求时延 P99。',
      unit: 's',
      query:
        histQuantile('sglang:e2e_request_latency_seconds', '0.99'),
      color: '#ff4d4f'
    },
    {
      name: 'sglang_ttft_p50',
      display_name: '首 Token 时延 P50',
      description: '最近 5 分钟 TTFT P50。',
      unit: 's',
      query:
        histQuantile('sglang:time_to_first_token_seconds', '0.50'),
      color: '#91caff'
    },
    {
      name: 'sglang_ttft_p90',
      display_name: '首 Token 时延 P90',
      description: '最近 5 分钟 TTFT P90。',
      unit: 's',
      query:
        histQuantile('sglang:time_to_first_token_seconds', '0.90'),
      color: '#4096ff'
    },
    {
      name: 'sglang_ttft_avg',
      display_name: '首 Token 时延均值',
      description: '最近 5 分钟 TTFT 均值。',
      unit: 's',
      query:
        'sum(rate(sglang:time_to_first_token_seconds_sum{__$labels__}[5m])) / sum(rate(sglang:time_to_first_token_seconds_count{__$labels__}[5m]))',
      color: '#69b1ff'
    },
    {
      name: 'sglang_e2e_p50',
      display_name: '端到端时延 P50',
      description: '最近 5 分钟端到端请求时延 P50。',
      unit: 's',
      query:
        histQuantile('sglang:e2e_request_latency_seconds', '0.50'),
      color: '#ffa39e'
    },
    {
      name: 'sglang_e2e_p90',
      display_name: '端到端时延 P90',
      description: '最近 5 分钟端到端请求时延 P90。',
      unit: 's',
      query:
        histQuantile('sglang:e2e_request_latency_seconds', '0.90'),
      color: '#ff7875'
    },
    {
      name: 'sglang_e2e_avg',
      display_name: '端到端时延均值',
      description: '最近 5 分钟端到端请求时延均值。',
      unit: 's',
      query:
        'sum(rate(sglang:e2e_request_latency_seconds_sum{__$labels__}[5m])) / sum(rate(sglang:e2e_request_latency_seconds_count{__$labels__}[5m]))',
      color: '#ff9c6e'
    }
  ],
  summaryCards: [
    {
      title: '运行中请求数',
      metric: 'sglang_running_reqs',
      unit: 'counts',
      color: '#2f6bff',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '运行中请求',
          detail: '正在处理的请求数，与排队同步抬升时需关注服务容量。'
        }
      ],
      footer: [{ label: '排队请求', metric: 'sglang_queue_reqs', unit: 'counts' }]
    },
    {
      title: '排队请求数',
      metric: 'sglang_queue_reqs',
      unit: 'counts',
      color: '#faad14',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '排队请求',
          detail: '等待队列长度，持续非零说明请求已积压。'
        }
      ],
      footer: [{ label: '运行中', metric: 'sglang_running_reqs', unit: 'counts' }]
    },
    {
      title: 'Token 用量',
      metric: 'sglang_token_usage',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'Token 用量',
          detail: 'KV/token 占用比例，接近满载时更容易排队。'
        }
      ],
      footer: [{ label: '缓存命中率', metric: 'sglang_cache_hit_rate', unit: 'percent' }]
    },
    {
      title: '缓存命中率',
      metric: 'sglang_cache_hit_rate',
      unit: 'percent',
      color: '#27c274',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '缓存命中',
          detail: 'Prefix cache 命中率越高，prefill 成本通常越低。'
        }
      ],
      footer: [{ label: '生成吞吐', metric: 'sglang_gen_throughput', unit: 'cps' }]
    },
    {
      title: '生成吞吐',
      metric: 'sglang_gen_throughput',
      unit: 'cps',
      color: '#597ef7',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '生成吞吐',
          detail: '当前生成吞吐（token/s），反映即时 decode 能力。'
        }
      ],
      footer: [
        { label: 'TTFT P90', metric: 'sglang_ttft_p90', unit: 's' },
        { label: 'E2E P90', metric: 'sglang_e2e_p90', unit: 's' }
      ]
    }
  ],
  charts: [
    {
      title: '请求队列趋势',
      subtitle: '运行中 / 排队',
      metric: 'sglang_running_reqs',
      guide: [
        {
          label: '队列趋势',
          detail: '运行中与排队请求随时间变化，排队抬升即需扩容或限流。'
        }
      ],
      series: [
        {
          metric: 'sglang_running_reqs',
          label: '运行中',
          color: '#2f6bff',
          unit: 'counts'
        },
        {
          metric: 'sglang_queue_reqs',
          label: '排队',
          color: '#faad14',
          unit: 'counts'
        }
      ]
    },
    {
      title: 'Token 吞吐趋势',
      subtitle: 'Prefill / Generation / 即时吞吐',
      metric: 'sglang_generation_tokens_rate',
      guide: [
        {
          label: 'Token 吞吐',
          detail: 'Prefill、累计生成速率与即时吞吐对比。'
        }
      ],
      series: [
        {
          metric: 'sglang_prompt_tokens_rate',
          label: 'Prefill',
          color: '#13c2c2',
          unit: 'cps'
        },
        {
          metric: 'sglang_generation_tokens_rate',
          label: 'Generation',
          color: '#27c274',
          unit: 'cps'
        },
        {
          metric: 'sglang_gen_throughput',
          label: '即时吞吐',
          color: '#597ef7',
          unit: 'cps'
        }
      ]
    },
    {
      title: 'TTFT 多分位',
      subtitle: 'P50 / P90 / P99 / 均值',
      metric: 'sglang_ttft_p99',
      guide: [
        {
          label: 'TTFT',
          detail: '首 token 时延多分位，对齐官方 Grafana 时延盘。'
        }
      ],
      series: [
        { metric: 'sglang_ttft_p50', label: 'P50', color: '#91caff', unit: 's' },
        { metric: 'sglang_ttft_p90', label: 'P90', color: '#4096ff', unit: 's' },
        { metric: 'sglang_ttft_p99', label: 'P99', color: '#597ef7', unit: 's' },
        { metric: 'sglang_ttft_avg', label: '均值', color: '#69b1ff', unit: 's' }
      ]
    },
    {
      title: 'E2E 多分位',
      subtitle: 'P50 / P90 / P99 / 均值',
      metric: 'sglang_e2e_p99',
      guide: [
        {
          label: 'E2E',
          detail: '端到端请求时延多分位，反映完整请求体验。'
        }
      ],
      series: [
        { metric: 'sglang_e2e_p50', label: 'P50', color: '#ffa39e', unit: 's' },
        { metric: 'sglang_e2e_p90', label: 'P90', color: '#ff7875', unit: 's' },
        { metric: 'sglang_e2e_p99', label: 'P99', color: '#ff4d4f', unit: 's' },
        { metric: 'sglang_e2e_avg', label: '均值', color: '#ff9c6e', unit: 's' }
      ]
    }
  ],
  statusPanels: [],
  details: [],
  ringPanels: [
    {
      title: '请求队列分布',
      subtitle: '运行中 / 排队',
      centerMetric: 'sglang_running_reqs',
      centerCaption: '运行中',
      centerUnit: 'counts',
      // 空闲实例 gauge 常为 0；全 0 占比无业务含义，与时延等面板统一为空态。
      emptyWhenAllZero: true,
      guide: [
        {
          label: '队列分布',
          detail: '运行中与排队请求占比，排队段扩大表示调度压力升高。'
        }
      ],
      segments: [
        {
          label: '运行中',
          metric: 'sglang_running_reqs',
          color: '#2f6bff',
          unit: 'counts'
        },
        {
          label: '排队',
          metric: 'sglang_queue_reqs',
          color: '#faad14',
          unit: 'counts'
        }
      ]
    }
  ],
  barPanels: []
};
