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
    },
    {
      name: 'activemq_topics_net_enqueue_rate',
      display_name: '净流入速率',
      description: '入队速率 − 出队速率；持续 >0 说明生产快于消费、积压扩大，<0 说明积压在缩小。',
      unit: 'cps',
      query: 'rate(activemq_topics_enqueue_count{__$labels__}[5m]) - rate(activemq_topics_dequeue_count{__$labels__}[5m])',
      color: '#ff8a1f'
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
      guide: [{ label: '当前积压', detail: 'Topic 当前存储消息数量，持续升高时说明消费落后于生产。' }]
    },
    {
      title: '净流入速率',
      metric: 'activemq_topics_net_enqueue_rate',
      unit: 'cps',
      color: '#ff8a1f',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '净流入速率', detail: '入队速率 − 出队速率；持续 >0 积压扩大，<0 积压在缩小。' }],
      footer: [{ label: '当前积压', metric: 'activemq_topics_size', unit: 'counts' }]
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
      unit: 'cps',
      color: '#27c274',
      icon: 'thunder',
      guide: [{ label: '出队速率', detail: 'Topic 每秒出队消息数量，反映消费侧处理能力。' }],
      footer: [{ label: '当前积压', metric: 'activemq_topics_size', unit: 'counts' }]
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
      title: '入出队总量趋势',
      subtitle: '累计入队与出队消息',
      metric: 'activemq_topics_enqueue_count',
      guide: [{ label: '入出队总量', detail: '对比 Topic 累计入队与出队消息数，两线差值即当前积压。' }],
      series: [
        { metric: 'activemq_topics_enqueue_count', label: '入队总量', color: '#2f6bff', unit: 'counts' },
        { metric: 'activemq_topics_dequeue_count', label: '出队总量', color: '#27c274', unit: 'counts' }
      ]
    },
    {
      title: '当前积压趋势',
      subtitle: '主题未消费消息数',
      metric: 'activemq_topics_size',
      guide: [{ label: '当前积压', detail: 'Topic 当前存储消息数量，持续升高说明消费落后于生产。' }],
      series: [
        { metric: 'activemq_topics_size', label: '当前积压', color: '#ff8a1f', unit: 'counts' }
      ]
    },
    {
      title: '消费者数趋势',
      subtitle: '主题消费者连接数',
      metric: 'activemq_topics_consumer_count',
      guide: [{ label: '消费者数', detail: '当前 Topic 消费者连接数，降为 0 即积压无人处理。' }],
      series: [
        { metric: 'activemq_topics_consumer_count', label: '消费者数', color: '#2f6bff', unit: 'counts' }
      ]
    }
  ],
  // 入出队总量/积压/消费者均已改为「积压与消费」分区下的独立折线图,不再用 detail 卡片。
  details: [],
  ringPanels: [],
  barPanels: []
};
