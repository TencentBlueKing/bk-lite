import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

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
      query: "sum(vllm:num_requests_running_gauge{__$labels__})",
      color: '#2f6bff'
    },
    {
      name: 'vllm_requests_waiting',
      display_name: '排队请求数',
      description: '当前等待调度容量的请求数量。',
      unit: 'counts',
      query: "sum(vllm:num_requests_waiting_gauge{__$labels__})",
      color: '#faad14'
    },
    {
      name: 'vllm_kv_cache_usage',
      display_name: 'KV 缓存占用',
      description: '已使用 KV cache 块占比（0–100%）。',
      unit: 'percent',
      query:
        "clamp_max(100 * avg(vllm:kv_cache_usage_perc_gauge{__$labels__}), 100)",
      color: '#ff8a1f'
    },
    {
      name: 'vllm_prompt_tokens_rate',
      display_name: 'Prefill Token 速率',
      description: '最近 5 分钟 prompt（prefill）token 处理速率。',
      unit: 'cps',
      query: "sum(rate(vllm:prompt_tokens_total_counter{__$labels__}[5m]))",
      color: '#13c2c2'
    },
    {
      name: 'vllm_generation_tokens_rate',
      display_name: '生成 Token 速率',
      description: '最近 5 分钟生成 token 速率。',
      unit: 'cps',
      query: "sum(rate(vllm:generation_tokens_total_counter{__$labels__}[5m]))",
      color: '#27c274'
    },
    {
      name: 'vllm_ttft_p99',
      display_name: '首 Token 时延 P99',
      description: '最近 5 分钟 Time-to-First-Token（TTFT）P99。',
      unit: 's',
      query:
        'histogram_quantile(0.99, sum(rate((label_replace({__name__=~"vllm:time_to_first_token_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:time_to_first_token_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:time_to_first_token_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#597ef7'
    },
    {
      name: 'vllm_e2e_p99',
      display_name: '端到端时延 P99',
      description: '最近 5 分钟端到端请求时延 P99。',
      unit: 's',
      query:
        'histogram_quantile(0.99, sum(rate((label_replace({__name__=~"vllm:e2e_request_latency_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:e2e_request_latency_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:e2e_request_latency_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#ff4d4f'
    },
    {
      name: 'vllm_success_rate',
      display_name: '成功请求速率',
      description: '最近 5 分钟成功完成请求速率。',
      unit: 'cps',
      query: "sum(rate(vllm:request_success_total_counter{__$labels__}[5m]))",
      color: '#27c274'
    },
    {
      name: 'vllm_ttft_p50',
      display_name: '首 Token 时延 P50',
      description: '最近 5 分钟 TTFT P50。',
      unit: 's',
      query:
        'histogram_quantile(0.50, sum(rate((label_replace({__name__=~"vllm:time_to_first_token_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:time_to_first_token_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:time_to_first_token_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#91caff'
    },
    {
      name: 'vllm_ttft_p90',
      display_name: '首 Token 时延 P90',
      description: '最近 5 分钟 TTFT P90。',
      unit: 's',
      query:
        'histogram_quantile(0.90, sum(rate((label_replace({__name__=~"vllm:time_to_first_token_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:time_to_first_token_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:time_to_first_token_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#4096ff'
    },
    {
      name: 'vllm_ttft_avg',
      display_name: '首 Token 时延均值',
      description: '最近 5 分钟 TTFT 均值。',
      unit: 's',
      query:
        'sum(rate(vllm:time_to_first_token_seconds_sum{__$labels__}[5m])) / sum(rate(vllm:time_to_first_token_seconds_count{__$labels__}[5m]))',
      color: '#69b1ff'
    },
    {
      name: 'vllm_e2e_p50',
      display_name: '端到端时延 P50',
      description: '最近 5 分钟端到端请求时延 P50。',
      unit: 's',
      query:
        'histogram_quantile(0.50, sum(rate((label_replace({__name__=~"vllm:e2e_request_latency_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:e2e_request_latency_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:e2e_request_latency_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#ffa39e'
    },
    {
      name: 'vllm_e2e_p90',
      display_name: '端到端时延 P90',
      description: '最近 5 分钟端到端请求时延 P90。',
      unit: 's',
      query:
        'histogram_quantile(0.90, sum(rate((label_replace({__name__=~"vllm:e2e_request_latency_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:e2e_request_latency_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:e2e_request_latency_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#ff7875'
    },
    {
      name: 'vllm_e2e_avg',
      display_name: '端到端时延均值',
      description: '最近 5 分钟端到端请求时延均值。',
      unit: 's',
      query:
        'sum(rate(vllm:e2e_request_latency_seconds_sum{__$labels__}[5m])) / sum(rate(vllm:e2e_request_latency_seconds_count{__$labels__}[5m]))',
      color: '#ff9c6e'
    },
    {
      name: 'vllm_itl_p50',
      display_name: '逐 Token 时延 P50',
      description: '最近 5 分钟 ITL P50。',
      unit: 's',
      query:
        'histogram_quantile(0.50, sum(rate((label_replace({__name__=~"vllm:inter_token_latency_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:inter_token_latency_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:inter_token_latency_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#b37feb'
    },
    {
      name: 'vllm_itl_p90',
      display_name: '逐 Token 时延 P90',
      description: '最近 5 分钟 ITL P90。',
      unit: 's',
      query:
        'histogram_quantile(0.90, sum(rate((label_replace({__name__=~"vllm:inter_token_latency_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:inter_token_latency_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:inter_token_latency_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#9254de'
    },
    {
      name: 'vllm_itl_p99',
      display_name: '逐 Token 时延 P99',
      description: '最近 5 分钟 ITL P99。',
      unit: 's',
      query:
        'histogram_quantile(0.99, sum(rate((label_replace({__name__=~"vllm:inter_token_latency_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:inter_token_latency_seconds_(.+)"))[5m:]) or label_replace(rate(vllm:inter_token_latency_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#722ed1'
    },
    {
      name: 'vllm_itl_avg',
      display_name: '逐 Token 时延均值',
      description: '最近 5 分钟 ITL 均值。',
      unit: 's',
      query:
        'sum(rate(vllm:inter_token_latency_seconds_sum{__$labels__}[5m])) / sum(rate(vllm:inter_token_latency_seconds_count{__$labels__}[5m]))',
      color: '#531dab'
    },
    {
      name: 'vllm_iteration_tokens_rate',
      display_name: '迭代 Token 速率',
      description: '最近 5 分钟单次模型迭代处理的 token 数速率。',
      unit: 'cps',
      query: 'sum(rate(vllm:iteration_tokens_total_count{__$labels__}[5m]))',
      color: '#36cfc9'
    },
    {
      name: 'vllm_prompt_tokens_p50',
      display_name: '输入 Token 长度 P50',
      description: '最近 5 分钟请求 prompt token 数 P50。',
      unit: 'counts',
      query:
        'histogram_quantile(0.50, sum(rate((label_replace({__name__=~"vllm:request_prompt_tokens_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:request_prompt_tokens_(.+)"))[5m:]) or label_replace(rate(vllm:request_prompt_tokens_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#5cdbd3'
    },
    {
      name: 'vllm_prompt_tokens_p90',
      display_name: '输入 Token 长度 P90',
      description: '最近 5 分钟请求 prompt token 数 P90。',
      unit: 'counts',
      query:
        'histogram_quantile(0.90, sum(rate((label_replace({__name__=~"vllm:request_prompt_tokens_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:request_prompt_tokens_(.+)"))[5m:]) or label_replace(rate(vllm:request_prompt_tokens_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#13c2c2'
    },
    {
      name: 'vllm_prompt_tokens_p99',
      display_name: '输入 Token 长度 P99',
      description: '最近 5 分钟请求 prompt token 数 P99。',
      unit: 'counts',
      query:
        'histogram_quantile(0.99, sum(rate((label_replace({__name__=~"vllm:request_prompt_tokens_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:request_prompt_tokens_(.+)"))[5m:]) or label_replace(rate(vllm:request_prompt_tokens_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#08979c'
    },
    {
      name: 'vllm_prompt_tokens_avg',
      display_name: '输入 Token 长度均值',
      description: '最近 5 分钟请求 prompt token 数均值。',
      unit: 'counts',
      query:
        'sum(rate(vllm:request_prompt_tokens_sum{__$labels__}[5m])) / sum(rate(vllm:request_prompt_tokens_count{__$labels__}[5m]))',
      color: '#006d75'
    },
    {
      name: 'vllm_generation_tokens_p50',
      display_name: '输出 Token 长度 P50',
      description: '最近 5 分钟请求生成 token 数 P50。',
      unit: 'counts',
      query:
        'histogram_quantile(0.50, sum(rate((label_replace({__name__=~"vllm:request_generation_tokens_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:request_generation_tokens_(.+)"))[5m:]) or label_replace(rate(vllm:request_generation_tokens_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#95de64'
    },
    {
      name: 'vllm_generation_tokens_p90',
      display_name: '输出 Token 长度 P90',
      description: '最近 5 分钟请求生成 token 数 P90。',
      unit: 'counts',
      query:
        'histogram_quantile(0.90, sum(rate((label_replace({__name__=~"vllm:request_generation_tokens_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:request_generation_tokens_(.+)"))[5m:]) or label_replace(rate(vllm:request_generation_tokens_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#73d13d'
    },
    {
      name: 'vllm_generation_tokens_p99',
      display_name: '输出 Token 长度 P99',
      description: '最近 5 分钟请求生成 token 数 P99。',
      unit: 'counts',
      query:
        'histogram_quantile(0.99, sum(rate((label_replace({__name__=~"vllm:request_generation_tokens_[0-9.]+", __$labels__}, "le", "$1", "__name__", "vllm:request_generation_tokens_(.+)"))[5m:]) or label_replace(rate(vllm:request_generation_tokens_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (le))',
      color: '#52c41a'
    },
    {
      name: 'vllm_generation_tokens_avg',
      display_name: '输出 Token 长度均值',
      description: '最近 5 分钟请求生成 token 数均值。',
      unit: 'counts',
      query:
        'sum(rate(vllm:request_generation_tokens_sum{__$labels__}[5m])) / sum(rate(vllm:request_generation_tokens_count{__$labels__}[5m]))',
      color: '#389e0d'
    }
  ],
  summaryCards: [
    {
      title: '运行中请求数',
      metric: 'vllm_requests_running',
      unit: 'counts',
      color: '#2f6bff',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '运行中请求',
          detail: '正在执行批次中的请求数，持续抬升且排队同步增加时需关注算力瓶颈。'
        }
      ],
      footer: [{ label: '排队请求', metric: 'vllm_requests_waiting', unit: 'counts' }]
    },
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
          detail: '等待调度容量的请求数，持续非零说明吞吐已接近上限。'
        }
      ],
      footer: [{ label: '运行中', metric: 'vllm_requests_running', unit: 'counts' }]
    },
    {
      title: 'KV 缓存占用',
      metric: 'vllm_kv_cache_usage',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'KV 缓存',
          detail: 'KV cache 块占用比例，接近 100% 时新请求更容易排队或抢占。'
        }
      ],
      footer: [{ label: '排队请求', metric: 'vllm_requests_waiting', unit: 'counts' }]
    },
    {
      title: '生成 Token 速率',
      metric: 'vllm_generation_tokens_rate',
      unit: 'cps',
      color: '#27c274',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '生成吞吐',
          detail: '生成 token 速率，反映 decode 阶段有效吞吐。'
        }
      ],
      footer: [
        { label: 'Prefill 速率', metric: 'vllm_prompt_tokens_rate', unit: 'cps' },
        { label: '成功请求', metric: 'vllm_success_rate', unit: 'cps' }
      ]
    },
    {
      title: '首 Token 时延 P99',
      metric: 'vllm_ttft_p99',
      unit: 's',
      color: '#597ef7',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'TTFT P99',
          detail: '首 token 时延 P99，抬升通常与 prefill 排队或 KV 压力相关。'
        }
      ],
      footer: [
        { label: 'E2E P99', metric: 'vllm_e2e_p99', unit: 's' },
        { label: 'ITL P99', metric: 'vllm_itl_p99', unit: 's' }
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
          detail: '运行中与排队请求随时间变化，排队曲线抬升即需扩容或限流。'
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
      title: 'Token 吞吐趋势',
      subtitle: 'Prefill / Generation / 迭代',
      metric: 'vllm_generation_tokens_rate',
      guide: [
        {
          label: 'Token 吞吐',
          detail: 'Prefill、生成 token 速率与单次迭代 token 速率对比。'
        }
      ],
      series: [
        {
          metric: 'vllm_prompt_tokens_rate',
          label: 'Prefill',
          color: '#13c2c2',
          unit: 'cps'
        },
        {
          metric: 'vllm_generation_tokens_rate',
          label: 'Generation',
          color: '#27c274',
          unit: 'cps'
        },
        {
          metric: 'vllm_iteration_tokens_rate',
          label: '迭代',
          color: '#36cfc9',
          unit: 'cps'
        },
        {
          metric: 'vllm_success_rate',
          label: '成功请求',
          color: '#389e0d',
          unit: 'cps'
        }
      ]
    },
    {
      title: 'TTFT 多分位',
      subtitle: 'P50 / P90 / P99 / 均值',
      metric: 'vllm_ttft_p99',
      guide: [
        {
          label: 'TTFT',
          detail: '首 token 时延多分位，对比尾部与典型用户体验。'
        }
      ],
      series: [
        { metric: 'vllm_ttft_p50', label: 'P50', color: '#91caff', unit: 's' },
        { metric: 'vllm_ttft_p90', label: 'P90', color: '#4096ff', unit: 's' },
        { metric: 'vllm_ttft_p99', label: 'P99', color: '#597ef7', unit: 's' },
        { metric: 'vllm_ttft_avg', label: '均值', color: '#69b1ff', unit: 's' }
      ]
    },
    {
      title: 'E2E 多分位',
      subtitle: 'P50 / P90 / P99 / 均值',
      metric: 'vllm_e2e_p99',
      guide: [
        {
          label: 'E2E',
          detail: '端到端请求时延多分位，反映完整请求体验。'
        }
      ],
      series: [
        { metric: 'vllm_e2e_p50', label: 'P50', color: '#ffa39e', unit: 's' },
        { metric: 'vllm_e2e_p90', label: 'P90', color: '#ff7875', unit: 's' },
        { metric: 'vllm_e2e_p99', label: 'P99', color: '#ff4d4f', unit: 's' },
        { metric: 'vllm_e2e_avg', label: '均值', color: '#ff9c6e', unit: 's' }
      ]
    },
    {
      title: 'ITL 多分位',
      subtitle: 'P50 / P90 / P99 / 均值',
      metric: 'vllm_itl_p99',
      guide: [
        {
          label: 'ITL',
          detail: '逐 token 生成时延（Inter-Token Latency），decode 阶段核心指标。'
        }
      ],
      series: [
        { metric: 'vllm_itl_p50', label: 'P50', color: '#b37feb', unit: 's' },
        { metric: 'vllm_itl_p90', label: 'P90', color: '#9254de', unit: 's' },
        { metric: 'vllm_itl_p99', label: 'P99', color: '#722ed1', unit: 's' },
        { metric: 'vllm_itl_avg', label: '均值', color: '#531dab', unit: 's' }
      ]
    },
    {
      title: '输入 Token 长度',
      subtitle: 'P50 / P90 / P99 / 均值',
      metric: 'vllm_prompt_tokens_p99',
      guide: [
        {
          label: '输入长度',
          detail: '请求 prompt token 数分布，异常抬升可能带来 prefill 压力。'
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
          detail: '请求生成 token 数分布，对齐官方 Query Statistics 输出侧指标。'
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
      guide: [
        {
          label: '队列分布',
          detail: '运行中与排队请求占比，排队段扩大表示调度压力升高。'
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
