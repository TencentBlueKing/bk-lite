import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const LLAMASERVER_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'llamaserver',
  pageTitle: 'llama-server 监控仪表盘',
  objectFallbackName: 'LlamaServer',
  instanceType: 'llamaserver',
  collectionStatusQuery:
    "count({instance_type='llamaserver', collect_type='bkpull', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'bkpull', 'Prometheus'],
  metrics: [
    {
      name: 'llamacpp_processing',
      display_name: '处理中请求数',
      description: '当前正在处理的请求数量。',
      unit: 'counts',
      query: "sum(llamacpp:requests_processing_gauge{__$labels__})",
      color: '#2f6bff'
    },
    {
      name: 'llamacpp_deferred',
      display_name: '延迟请求数',
      description: '当前被延迟（deferred）的请求数量。',
      unit: 'counts',
      query: "sum(llamacpp:requests_deferred_gauge{__$labels__})",
      color: '#faad14'
    },
    {
      name: 'llamacpp_kv_usage',
      display_name: 'KV 缓存占用',
      description: 'KV cache 占用比例（0–100%）。',
      unit: 'percent',
      query:
        "clamp_max(100 * avg(llamacpp:kv_cache_usage_ratio_gauge{__$labels__}), 100)",
      color: '#ff8a1f'
    },
    {
      name: 'llamacpp_prompt_tokens_rate',
      display_name: 'Prompt Token 速率',
      description: '最近 5 分钟 prompt token 处理速率。',
      unit: 'cps',
      query: "sum(rate(llamacpp:prompt_tokens_total_counter{__$labels__}[5m]))",
      color: '#13c2c2'
    },
    {
      name: 'llamacpp_predicted_tokens_rate',
      display_name: '生成 Token 速率',
      description: '最近 5 分钟生成（predicted）token 速率。',
      unit: 'cps',
      query: "sum(rate(llamacpp:tokens_predicted_total_counter{__$labels__}[5m]))",
      color: '#27c274'
    },
    {
      name: 'llamacpp_prompt_tps',
      display_name: 'Prompt 平均吞吐',
      description: 'Prompt 平均吞吐（tokens/s）。',
      unit: 'cps',
      query: "avg(llamacpp:prompt_tokens_seconds_gauge{__$labels__})",
      color: '#597ef7'
    },
    {
      name: 'llamacpp_predicted_tps',
      display_name: '生成平均吞吐',
      description: '生成平均吞吐（tokens/s）。',
      unit: 'cps',
      query: "avg(llamacpp:predicted_tokens_seconds_gauge{__$labels__})",
      color: '#27c274'
    },
    {
      name: 'llamacpp_decode_rate',
      display_name: 'Decode 调用速率',
      description: '最近 5 分钟 llama_decode() 调用速率。',
      unit: 'cps',
      query: "sum(rate(llamacpp:n_decode_total_counter{__$labels__}[5m]))",
      color: '#722ed1'
    },
    {
      name: 'llamacpp_busy_slots',
      display_name: 'Decode 平均忙槽位',
      description: '每次 llama_decode() 调用平均 busy slot 数。',
      unit: 'counts',
      query: "avg(llamacpp:n_busy_slots_per_decode_counter{__$labels__})",
      color: '#9254de'
    },
    {
      name: 'llamacpp_tokens_per_decode',
      display_name: '每次 Decode Token 数',
      description: '最近 5 分钟每次 decode 平均处理的 predicted token 数。',
      unit: 'counts',
      query:
        'sum(rate(llamacpp:tokens_predicted_total_counter{__$labels__}[5m])) / sum(rate(llamacpp:n_decode_total_counter{__$labels__}[5m]))',
      color: '#531dab'
    },
    {
      name: 'llamacpp_prompt_tokens_total',
      display_name: '累计 Prompt Token',
      description: '自启动以来累计处理的 prompt token 总数。',
      unit: 'counts',
      query: "sum(llamacpp:prompt_tokens_total_counter{__$labels__})",
      color: '#08979c'
    },
    {
      name: 'llamacpp_predicted_tokens_total',
      display_name: '累计生成 Token',
      description: '自启动以来累计生成的 token 总数。',
      unit: 'counts',
      query: "sum(llamacpp:tokens_predicted_total_counter{__$labels__})",
      color: '#006d75'
    }
  ],
  summaryCards: [
    {
      title: '处理中请求数',
      metric: 'llamacpp_processing',
      unit: 'counts',
      color: '#2f6bff',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '处理中请求',
          detail: '正在处理的请求数，与延迟请求同步抬升时需关注服务容量。'
        }
      ],
      footer: [{ label: '延迟请求', metric: 'llamacpp_deferred', unit: 'counts' }]
    },
    {
      title: '延迟请求数',
      metric: 'llamacpp_deferred',
      unit: 'counts',
      color: '#faad14',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '延迟请求',
          detail: 'deferred 请求数，持续非零说明服务已开始积压。'
        }
      ],
      footer: [{ label: '处理中', metric: 'llamacpp_processing', unit: 'counts' }]
    },
    {
      title: 'KV 缓存占用',
      metric: 'llamacpp_kv_usage',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'KV 缓存',
          detail: 'KV cache 占用比例，接近满载时新请求更容易被延迟。'
        }
      ],
      footer: [{ label: '延迟请求', metric: 'llamacpp_deferred', unit: 'counts' }]
    },
    {
      title: '生成平均吞吐',
      metric: 'llamacpp_predicted_tps',
      unit: 'cps',
      color: '#27c274',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '生成吞吐',
          detail: '生成平均吞吐（tokens/s），反映 decode 阶段能力。'
        }
      ],
      footer: [{ label: 'Prompt 吞吐', metric: 'llamacpp_prompt_tps', unit: 'cps' }]
    },
    {
      title: '生成 Token 速率',
      metric: 'llamacpp_predicted_tokens_rate',
      unit: 'cps',
      color: '#597ef7',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '生成速率',
          detail: '最近 5 分钟 predicted token 速率。'
        }
      ],
      footer: [
        { label: 'Decode 速率', metric: 'llamacpp_decode_rate', unit: 'cps' },
        { label: 'Tokens/Decode', metric: 'llamacpp_tokens_per_decode', unit: 'counts' }
      ]
    }
  ],
  charts: [
    {
      title: '请求队列趋势',
      subtitle: '处理中 / 延迟',
      metric: 'llamacpp_processing',
      guide: [
        {
          label: '队列趋势',
          detail: '处理中与 deferred 请求随时间变化，延迟曲线抬升即需关注。'
        }
      ],
      series: [
        {
          metric: 'llamacpp_processing',
          label: '处理中',
          color: '#2f6bff',
          unit: 'counts'
        },
        {
          metric: 'llamacpp_deferred',
          label: '延迟',
          color: '#faad14',
          unit: 'counts'
        }
      ]
    },
    {
      title: 'Token 吞吐趋势',
      subtitle: '累计速率 / 平均吞吐',
      metric: 'llamacpp_predicted_tokens_rate',
      guide: [
        {
          label: 'Token 吞吐',
          detail: 'Prompt/生成累计速率与平均吞吐对比。'
        }
      ],
      series: [
        {
          metric: 'llamacpp_prompt_tokens_rate',
          label: 'Prompt 速率',
          color: '#13c2c2',
          unit: 'cps'
        },
        {
          metric: 'llamacpp_predicted_tokens_rate',
          label: '生成速率',
          color: '#27c274',
          unit: 'cps'
        },
        {
          metric: 'llamacpp_predicted_tps',
          label: '生成平均吞吐',
          color: '#597ef7',
          unit: 'cps'
        }
      ]
    },
    {
      title: '平均吞吐对比',
      subtitle: 'Prompt / Generation',
      metric: 'llamacpp_prompt_tps',
      guide: [
        {
          label: '平均吞吐',
          detail: 'Prompt 与生成平均吞吐对比，评估两侧能力是否失衡。'
        }
      ],
      series: [
        {
          metric: 'llamacpp_prompt_tps',
          label: 'Prompt 吞吐',
          color: '#13c2c2',
          unit: 'cps'
        },
        {
          metric: 'llamacpp_predicted_tps',
          label: '生成吞吐',
          color: '#27c274',
          unit: 'cps'
        }
      ]
    },
    {
      title: 'Decode 效率',
      subtitle: '调用速率 / 忙槽位 / Tokens per Decode',
      metric: 'llamacpp_decode_rate',
      guide: [
        {
          label: 'Decode',
          detail: 'decode 调用速率、连续批处理忙槽位与每次 decode 处理的 token 数。'
        }
      ],
      series: [
        {
          metric: 'llamacpp_decode_rate',
          label: 'Decode 速率',
          color: '#722ed1',
          unit: 'cps'
        },
        {
          metric: 'llamacpp_busy_slots',
          label: '忙槽位',
          color: '#9254de',
          unit: 'counts'
        },
        {
          metric: 'llamacpp_tokens_per_decode',
          label: 'Tokens/Decode',
          color: '#531dab',
          unit: 'counts'
        }
      ]
    },
    {
      title: '累计 Token',
      subtitle: 'Prompt / Generation 总量',
      metric: 'llamacpp_predicted_tokens_total',
      guide: [
        {
          label: '累计 Token',
          detail: '自启动以来累计 prompt 与生成 token 总量。'
        }
      ],
      series: [
        {
          metric: 'llamacpp_prompt_tokens_total',
          label: 'Prompt 累计',
          color: '#08979c',
          unit: 'counts'
        },
        {
          metric: 'llamacpp_predicted_tokens_total',
          label: '生成累计',
          color: '#006d75',
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
      subtitle: '处理中 / 延迟',
      centerMetric: 'llamacpp_processing',
      centerCaption: '处理中',
      centerUnit: 'counts',
      // 空闲实例 gauge 常为 0；全 0 占比无业务含义，与时延等面板统一为空态。
      emptyWhenAllZero: true,
      guide: [
        {
          label: '队列分布',
          detail: '处理中与 deferred 请求占比，延迟段扩大表示积压升高。'
        }
      ],
      segments: [
        {
          label: '处理中',
          metric: 'llamacpp_processing',
          color: '#2f6bff',
          unit: 'counts'
        },
        {
          label: '延迟',
          metric: 'llamacpp_deferred',
          color: '#faad14',
          unit: 'counts'
        }
      ]
    }
  ],
  barPanels: []
};
