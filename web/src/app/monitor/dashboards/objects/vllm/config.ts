import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';
import { telegrafHistogramQuantile } from '../../shared/utils/telegrafHistogram';

/** Telegraf histogram bucket query; group by instance_id only (one scrape URL = one instance). */
const histQuantile = (base: string, quantile: string) => telegrafHistogramQuantile(base, quantile);

export const VLLM_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'vllm',
  pageTitle: 'vLLM 监控仪表盘',
  objectFallbackName: 'VLLM',
  instanceType: 'vllm',
  collectionStatusQuery:
    "count({instance_type='vllm', collect_type='bkpull', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'bkpull', 'Prometheus'],
  metrics: [
    {
      name: 'vllm_requests_running',
      display_name: '运行中请求数',
      description: '当前正在模型执行批次中的请求数量。',
      unit: 'counts',
      query: 'sum by (instance_id) (vllm:num_requests_running_gauge{__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'vllm_requests_waiting',
      display_name: '排队请求数',
      description: '当前等待调度容量的请求数量。',
      unit: 'counts',
      query: 'sum by (instance_id) (vllm:num_requests_waiting_gauge{__$labels__})',
      color: '#faad14'
    },
    {
      name: 'vllm_kv_cache_usage',
      display_name: 'KV 缓存占用',
      description: '已使用 KV cache 块占比（0–100%）。',
      unit: 'percent',
      query:
        'clamp_max(100 * max by (instance_id) (vllm:kv_cache_usage_perc_gauge{__$labels__}), 100)',
      color: '#ff8a1f'
    },
    {
      name: 'vllm_ttft_p95',
      display_name: '首 Token 时延 P95',
      description: '最近 5 分钟 Time-to-First-Token（TTFT）P95。',
      unit: 's',
      query: histQuantile('vllm:time_to_first_token_seconds', '0.95'),
      color: '#597ef7'
    },
    {
      name: 'vllm_tpot_p95',
      display_name: 'TPOT P95',
      description: '最近 5 分钟 ITL / TPOT P95（逐 Token 时延）。',
      unit: 's',
      query: histQuantile('vllm:inter_token_latency_seconds', '0.95'),
      color: '#722ed1'
    },
    {
      name: 'vllm_qps',
      display_name: 'QPS',
      description: '最近 5 分钟成功完成请求速率。',
      unit: 'cps',
      query:
        'sum by (instance_id) (rate(vllm:request_success_total_counter{__$labels__}[5m]))',
      color: '#27c274'
    },
    {
      name: 'vllm_queue_p95',
      display_name: '排队时延 P95',
      description: '最近 5 分钟请求排队时延 P95。',
      unit: 's',
      query: histQuantile('vllm:request_queue_time_seconds', '0.95'),
      color: '#faad14'
    },
    {
      name: 'vllm_prefill_p95',
      display_name: 'Prefill 时延 P95',
      description: '最近 5 分钟 Prefill 时延 P95。',
      unit: 's',
      query: histQuantile('vllm:request_prefill_time_seconds', '0.95'),
      color: '#13c2c2'
    },
    {
      name: 'vllm_decode_p95',
      display_name: 'Decode 时延 P95',
      description: '最近 5 分钟 Decode 时延 P95。',
      unit: 's',
      query: histQuantile('vllm:request_decode_time_seconds', '0.95'),
      color: '#9254de'
    },
    {
      name: 'vllm_itl_p99',
      display_name: '逐 Token 时延 P99',
      description: '最近 5 分钟 ITL P99。',
      unit: 's',
      query: histQuantile('vllm:inter_token_latency_seconds', '0.99'),
      color: '#531dab'
    },
    {
      name: 'vllm_e2e_p95',
      display_name: '端到端时延 P95',
      description: '最近 5 分钟端到端请求时延 P95。',
      unit: 's',
      query: histQuantile('vllm:e2e_request_latency_seconds', '0.95'),
      color: '#ff7875'
    },
    {
      name: 'vllm_e2e_p99',
      display_name: '端到端时延 P99',
      description: '最近 5 分钟端到端请求时延 P99。',
      unit: 's',
      query: histQuantile('vllm:e2e_request_latency_seconds', '0.99'),
      color: '#ff4d4f'
    },
    {
      name: 'vllm_input_tpm',
      display_name: '输入 TPM',
      description: '最近 5 分钟 prompt token 吞吐。',
      unit: 'tpm',
      // tokens/min = rate * 60；不要套用 Grafana Output TPM *6。
      query:
        'sum by (instance_id) (rate(vllm:prompt_tokens_total_counter{__$labels__}[5m])) * 60',
      color: '#13c2c2'
    },
    {
      name: 'vllm_output_tpm',
      display_name: '输出 TPM',
      description: '最近 5 分钟 generation token 吞吐。',
      unit: 'tpm',
      // tokens/min = rate * 60；不要套用 Grafana Output TPM *6。
      query:
        'sum by (instance_id) (rate(vllm:generation_tokens_total_counter{__$labels__}[5m])) * 60',
      color: '#27c274'
    },
    {
      name: 'vllm_prompt_tokens_p50',
      display_name: '输入 Token 长度 P50',
      description: '最近 5 分钟请求 prompt token 数 P50。',
      unit: 'counts',
      query: histQuantile('vllm:request_prompt_tokens', '0.50'),
      color: '#5cdbd3'
    },
    {
      name: 'vllm_prompt_tokens_p90',
      display_name: '输入 Token 长度 P90',
      description: '最近 5 分钟请求 prompt token 数 P90。',
      unit: 'counts',
      query: histQuantile('vllm:request_prompt_tokens', '0.90'),
      color: '#13c2c2'
    },
    {
      name: 'vllm_prompt_tokens_p99',
      display_name: '输入 Token 长度 P99',
      description: '最近 5 分钟请求 prompt token 数 P99。',
      unit: 'counts',
      query: histQuantile('vllm:request_prompt_tokens', '0.99'),
      color: '#08979c'
    },
    {
      name: 'vllm_prompt_tokens_avg',
      display_name: '输入 Token 长度均值',
      description: '最近 5 分钟请求 prompt token 数均值。',
      unit: 'counts',
      query:
        'sum by (instance_id) (rate(vllm:request_prompt_tokens_sum{__$labels__}[5m])) / sum by (instance_id) (rate(vllm:request_prompt_tokens_count{__$labels__}[5m]))',
      color: '#006d75'
    },
    {
      name: 'vllm_generation_tokens_p50',
      display_name: '输出 Token 长度 P50',
      description: '最近 5 分钟请求生成 token 数 P50。',
      unit: 'counts',
      query: histQuantile('vllm:request_generation_tokens', '0.50'),
      color: '#95de64'
    },
    {
      name: 'vllm_generation_tokens_p90',
      display_name: '输出 Token 长度 P90',
      description: '最近 5 分钟请求生成 token 数 P90。',
      unit: 'counts',
      query: histQuantile('vllm:request_generation_tokens', '0.90'),
      color: '#73d13d'
    },
    {
      name: 'vllm_generation_tokens_p99',
      display_name: '输出 Token 长度 P99',
      description: '最近 5 分钟请求生成 token 数 P99。',
      unit: 'counts',
      query: histQuantile('vllm:request_generation_tokens', '0.99'),
      color: '#52c41a'
    },
    {
      name: 'vllm_generation_tokens_avg',
      display_name: '输出 Token 长度均值',
      description: '最近 5 分钟请求生成 token 数均值。',
      unit: 'counts',
      query:
        'sum by (instance_id) (rate(vllm:request_generation_tokens_sum{__$labels__}[5m])) / sum by (instance_id) (rate(vllm:request_generation_tokens_count{__$labels__}[5m]))',
      color: '#389e0d'
    }
  ],
  summaryCards: [
    {
      title: '排队请求数',
      metric: 'vllm_requests_waiting',
      unit: 'counts',
      color: '#faad14',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '排队请求',
          detail: '等待调度的请求数。'
        }
      ],
      footer: [
        { label: '运行中', metric: 'vllm_requests_running', unit: 'counts' },
        { label: '排队时延 P95', metric: 'vllm_queue_p95', unit: 's' }
      ]
    },
    {
      title: '首 Token 时延 P95',
      metric: 'vllm_ttft_p95',
      unit: 's',
      color: '#597ef7',
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'TTFT P95',
          detail: '首 Token 时延 P95。'
        }
      ],
      footer: [
        { label: 'Queue P95', metric: 'vllm_queue_p95', unit: 's' },
        { label: 'Prefill P95', metric: 'vllm_prefill_p95', unit: 's' }
      ]
    },
    {
      title: 'KV 缓存占用',
      metric: 'vllm_kv_cache_usage',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'KV 缓存',
          detail: 'KV cache 最高占用。'
        }
      ],
      footer: [{ label: '排队请求', metric: 'vllm_requests_waiting', unit: 'counts' }]
    },
    {
      title: 'TPOT P95',
      metric: 'vllm_tpot_p95',
      unit: 's',
      color: '#722ed1',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'TPOT P95',
          detail: '逐 Token 时延 P95。'
        }
      ],
      footer: [
        { label: 'E2E P95', metric: 'vllm_e2e_p95', unit: 's' },
        { label: 'Decode P95', metric: 'vllm_decode_p95', unit: 's' }
      ]
    },
    {
      title: 'QPS',
      metric: 'vllm_qps',
      unit: 'cps',
      color: '#27c274',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: 'QPS',
          detail: '成功完成请求速率。'
        }
      ],
      footer: [
        { label: '输入 TPM', metric: 'vllm_input_tpm', unit: 'tpm' },
        { label: '输出 TPM', metric: 'vllm_output_tpm', unit: 'tpm' }
      ]
    }
  ],
  charts: [
    {
      title: '请求队列趋势',
      subtitle: '运行中 / 排队',
      metric: 'vllm_requests_running',
      guide: [
        {
          label: '队列趋势',
          detail: '运行中与排队请求趋势。'
        }
      ],
      series: [
        {
          metric: 'vllm_requests_running',
          label: '运行中',
          color: '#2f6bff',
          unit: 'counts'
        },
        {
          metric: 'vllm_requests_waiting',
          label: '排队',
          color: '#faad14',
          unit: 'counts'
        }
      ]
    },
    {
      title: '时延拆解',
      subtitle: 'Queue / Prefill / Decode / TTFT P95',
      metric: 'vllm_ttft_p95',
      guide: [
        {
          label: '时延拆解',
          detail: '排队、Prefill、Decode 与 TTFT 的 P95。'
        }
      ],
      series: [
        { metric: 'vllm_queue_p95', label: 'Queue P95', color: '#faad14', unit: 's' },
        { metric: 'vllm_prefill_p95', label: 'Prefill P95', color: '#13c2c2', unit: 's' },
        { metric: 'vllm_decode_p95', label: 'Decode P95', color: '#9254de', unit: 's' },
        { metric: 'vllm_ttft_p95', label: 'TTFT P95', color: '#597ef7', unit: 's' }
      ]
    },
    {
      title: 'KV 缓存占用',
      subtitle: '最高占用',
      metric: 'vllm_kv_cache_usage',
      guide: [
        {
          label: 'KV 缓存',
          detail: '按实例取最高 KV 占用。'
        }
      ],
      series: [
        {
          metric: 'vllm_kv_cache_usage',
          label: 'KV max',
          color: '#ff8a1f',
          unit: 'percent'
        }
      ]
    },
    {
      title: 'ITL / E2E',
      subtitle: 'TPOT 与端到端 P95 / P99',
      metric: 'vllm_tpot_p95',
      guide: [
        {
          label: 'ITL / E2E',
          detail: '逐 Token 与端到端时延。'
        }
      ],
      series: [
        { metric: 'vllm_tpot_p95', label: 'ITL P95', color: '#722ed1', unit: 's' },
        { metric: 'vllm_itl_p99', label: 'ITL P99', color: '#531dab', unit: 's' },
        { metric: 'vllm_e2e_p95', label: 'E2E P95', color: '#ff7875', unit: 's' },
        { metric: 'vllm_e2e_p99', label: 'E2E P99', color: '#ff4d4f', unit: 's' }
      ]
    },
    {
      title: '输入 / 输出 TPM',
      subtitle: 'tpm',
      metric: 'vllm_output_tpm',
      guide: [
        {
          label: 'TPM',
          detail: '输入与输出 tokens per minute。'
        }
      ],
      series: [
        {
          metric: 'vllm_input_tpm',
          label: '输入 TPM',
          color: '#13c2c2',
          unit: 'tpm'
        },
        {
          metric: 'vllm_output_tpm',
          label: '输出 TPM',
          color: '#27c274',
          unit: 'tpm'
        }
      ]
    },
    {
      title: '输入 Token 长度',
      subtitle: 'P50 / P90 / P99 / 均值',
      metric: 'vllm_prompt_tokens_p99',
      guide: [
        {
          label: '输入长度',
          detail: '请求 prompt token 数分布。'
        }
      ],
      series: [
        {
          metric: 'vllm_prompt_tokens_p50',
          label: 'P50',
          color: '#5cdbd3',
          unit: 'counts'
        },
        {
          metric: 'vllm_prompt_tokens_p90',
          label: 'P90',
          color: '#13c2c2',
          unit: 'counts'
        },
        {
          metric: 'vllm_prompt_tokens_p99',
          label: 'P99',
          color: '#08979c',
          unit: 'counts'
        },
        {
          metric: 'vllm_prompt_tokens_avg',
          label: '均值',
          color: '#006d75',
          unit: 'counts'
        }
      ]
    },
    {
      title: '输出 Token 长度',
      subtitle: 'P50 / P90 / P99 / 均值',
      metric: 'vllm_generation_tokens_p99',
      guide: [
        {
          label: '输出长度',
          detail: '请求生成 token 数分布。'
        }
      ],
      series: [
        {
          metric: 'vllm_generation_tokens_p50',
          label: 'P50',
          color: '#95de64',
          unit: 'counts'
        },
        {
          metric: 'vllm_generation_tokens_p90',
          label: 'P90',
          color: '#73d13d',
          unit: 'counts'
        },
        {
          metric: 'vllm_generation_tokens_p99',
          label: 'P99',
          color: '#52c41a',
          unit: 'counts'
        },
        {
          metric: 'vllm_generation_tokens_avg',
          label: '均值',
          color: '#389e0d',
          unit: 'counts'
        }
      ]
    }
  ],
  statusPanels: [],
  details: [],
  ringPanels: [
    {
      title: '请求队列分布',
      subtitle: '运行中 / 排队',
      centerMetric: 'vllm_requests_running',
      centerCaption: '运行中',
      centerUnit: 'counts',
      // 空闲实例 gauge 常为 0；全 0 占比无业务含义，与时延等面板统一为空态。
      emptyWhenAllZero: true,
      guide: [
        {
          label: '队列分布',
          detail: '运行中与排队请求占比。'
        }
      ],
      segments: [
        {
          label: '运行中',
          metric: 'vllm_requests_running',
          color: '#2f6bff',
          unit: 'counts'
        },
        {
          label: '排队',
          metric: 'vllm_requests_waiting',
          color: '#faad14',
          unit: 'counts'
        }
      ]
    }
  ],
  barPanels: []
};
