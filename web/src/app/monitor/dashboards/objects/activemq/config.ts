import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const ACTIVEMQ_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'activemq',
  pageTitle: 'ActiveMQ 监控仪表盘',
  objectFallbackName: 'ActiveMQ',
  instanceType: 'activemq',
  collectionStatusQuery: "count({instance_type='activemq', collect_type='middleware', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'middleware', 'Topic'],
  metrics: [
    {
      name: 'activemq_topics_consumer_count',
      display_name: 'Topic 消费者数',
      description: '当前 Topic 消费者连接数量，反映消息消费能力。',
      unit: 'counts',
      query: 'activemq_topics_consumer_count{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'activemq_topics_dequeue_count',
      display_name: 'Topic 出队总量',
      description: 'Topic 累计出队消息数量。',
      unit: 'counts',
      query: 'activemq_topics_dequeue_count{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'activemq_topics_enqueue_count',
      display_name: 'Topic 入队总量',
      description: 'Topic 累计入队消息数量。',
      unit: 'counts',
      query: 'activemq_topics_enqueue_count{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'activemq_topics_size',
      display_name: 'Topic 当前积压',
      description: 'Topic 当前存储消息数量，反映积压状态。',
      unit: 'counts',
      query: 'activemq_topics_size{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'activemq_topics_dequeue_rate',
      display_name: 'Topic 出队速率',
      description: 'Topic 消息出队速率。',
      unit: 'cps',
      query: 'rate(activemq_topics_dequeue_count{__$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'activemq_topics_enqueue_rate',
      display_name: 'Topic 入队速率',
      description: 'Topic 消息入队速率。',
      unit: 'cps',
      query: 'rate(activemq_topics_enqueue_count{__$labels__}[5m])',
      color: '#2f6bff'
    }
  ],
  summaryCards: [
    {
      title: '当前积压',
      metric: 'activemq_topics_size',
      color: '#ff8a1f',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '当前积压', detail: 'Topic 当前存储消息数量，持续升高时说明消费落后于生产。' }],
      footer: [{ label: '消费者数', metric: 'activemq_topics_consumer_count', unit: 'counts' }]
    },
    {
      title: '消费者数',
      metric: 'activemq_topics_consumer_count',
      color: '#2f6bff',
      icon: 'node',
      guide: [{ label: '消费者', detail: '当前 Topic 消费者数量。消费者 = 0 即积压无人处理，需立即关注。' }],
      footer: [{ label: '当前积压', metric: 'activemq_topics_size', unit: 'counts' }]
    },
    {
      title: '入队速率',
      metric: 'activemq_topics_enqueue_rate',
      color: '#2f6bff',
      icon: 'thunder',
      guide: [{ label: '入队速率', detail: 'Topic 每秒入队消息数量，反映生产侧写入压力。' }],
      footer: [{ label: '当前积压', metric: 'activemq_topics_size', unit: 'counts' }]
    },
    {
      title: '出队速率',
      metric: 'activemq_topics_dequeue_rate',
      color: '#27c274',
      icon: 'thunder',
      guide: [{ label: '出队速率', detail: 'Topic 每秒出队消息数量，反映消费侧处理能力。' }],
      footer: [{ label: '消费者数', metric: 'activemq_topics_consumer_count', unit: 'counts' }]
    }
  ],
  charts: [
    {
      title: '消息吞吐趋势',
      subtitle: '入队、出队速率对比',
      metric: 'activemq_topics_enqueue_rate',
      guide: [{ label: '消息吞吐', detail: '对比 Topic 入队和出队速率，判断生产与消费是否平衡。剪刀差持续扩大说明消费滞后。' }],
      series: [
        { metric: 'activemq_topics_enqueue_rate', label: '入队速率', color: '#2f6bff', unit: 'cps' },
        { metric: 'activemq_topics_dequeue_rate', label: '出队速率', color: '#27c274', unit: 'cps' }
      ]
    },
    {
      title: '积压与消费趋势',
      subtitle: '当前积压、消费者数变化',
      metric: 'activemq_topics_size',
      guide: [{ label: '积压与消费', detail: '对比 Topic 积压消息数与消费者数量。积压升高而消费者不增，说明消费能力不足或消费者已掉线。' }],
      series: [
        { metric: 'activemq_topics_size', label: '积压', color: '#ff8a1f', unit: 'counts' },
        { metric: 'activemq_topics_consumer_count', label: '消费者', color: '#2f6bff', unit: 'counts' }
      ]
    }
  ],
  details: [
    {
      title: 'Topic 指标详情',
      subtitle: '吞吐、积压与消费者',
      rows: [
        { label: '入队总量(累计)', metric: 'activemq_topics_enqueue_count', unit: 'counts' },
        { label: '出队总量(累计)', metric: 'activemq_topics_dequeue_count', unit: 'counts' },
        { label: '当前积压', metric: 'activemq_topics_size', unit: 'counts' },
        { label: '消费者数', metric: 'activemq_topics_consumer_count', unit: 'counts' }
      ]
    }
  ],
  ringPanels: [],
  barPanels: []
};
