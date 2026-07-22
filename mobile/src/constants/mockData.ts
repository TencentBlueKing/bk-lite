import type { ChatItem } from '@/types/conversation';

export type { ChatItem };

export const mockChatData: ChatItem[] = [
  {
    id: '1',
    name: 'k8s平台监控工程师',
    avatar: '/avatars/01.png',
    lastMessage: '集群节点 CPU 使用率超过 85%，需要排查 Pod 负载',
    time: '14:56',
    website: '',
  },
  {
    id: '2',
    name: 'k8s平台架构师',
    avatar: '/avatars/02.png',
    lastMessage: '发现网络抖动，建议检查 CNI 插件及跨节点流量',
    time: '13:45',
    hasCall: true,
  },
  {
    id: '3',
    name: 'k8s运维工程师',
    avatar: '/avatars/03.png',
    lastMessage: 'API 响应码 500 增加，可能是后端服务超时或依赖异常',
    time: '12:30',
    hasCall: true,
  },
  {
    id: '4',
    name: 'ITSM服务台',
    avatar: '/avatars/04.png',
    lastMessage: '工单#1234：磁盘空间告警，/var 分区剩余 < 10%',
    time: '11:20',
  }
];

export interface ChatMessageRecord {
  chatId: string;
  chatName: string;
  chatAvatar: string;
  messageId: string;
  content: string;
  timestamp: number;
}

export const mockChatMessages: ChatMessageRecord[] = [
  {
    chatId: '1',
    chatName: 'k8s平台监控工程师',
    chatAvatar: '/avatars/01.png',
    messageId: 'm1-1',
    content: '告警：集群节点 node-01 CPU 使用率 92%，Pod 调度可能受到影响，请排查热点进程',
    timestamp: new Date('2025-10-30T14:56:00').getTime(),
  },
  {
    chatId: '1',
    chatName: 'k8s平台监控工程师',
    chatAvatar: '/avatars/01.png',
    messageId: 'm1-2',
    content: '建议查看 Prometheus 抓取间隔和 scrape 成功率，排查监控丢数据问题',
    timestamp: new Date('2025-10-30T10:30:00').getTime(),
  },
  {
    chatId: '1',
    chatName: 'k8s平台监控工程师',
    chatAvatar: '/avatars/01.png',
    messageId: 'm1-3',
    content: '已定位到高 CPU 进程：/usr/bin/heavy-worker，建议重启或限制资源',
    timestamp: new Date('2025-10-30T10:31:00').getTime(),
  },
  {
    chatId: '2',
    chatName: 'k8s平台架构师',
    chatAvatar: '/avatars/02.png',
    messageId: 'm2-1',
    content: '观察到跨可用区流量延迟增加，可能与 CNI 路由或网络策略有关',
    timestamp: new Date('2025-10-30T13:45:00').getTime(),
  },
  {
    chatId: '2',
    chatName: 'k8s平台架构师',
    chatAvatar: '/avatars/02.png',
    messageId: 'm2-2',
    content: '建议在非高峰时段切换 CNI 插件测试，以验证是否为插件引起的问题',
    timestamp: new Date('2025-10-29T16:20:00').getTime(),
  },
  {
    chatId: '2',
    chatName: 'k8s平台架构师',
    chatAvatar: '/avatars/02.png',
    messageId: 'm2-3',
    content: '已在 staging 环境复现网络抖动，准备下发补丁并回滚测试',
    timestamp: new Date('2025-10-29T16:21:00').getTime(),
  },
  {
    chatId: '3',
    chatName: 'k8s服务支撑工程师',
    chatAvatar: '/avatars/03.png',
    messageId: 'm3-1',
    content: '发现后端服务 svc-order 在 10:22 开始返回 500，可能为数据库连接池耗尽',
    timestamp: new Date('2025-10-30T12:30:00').getTime(),
  },
  {
    chatId: '3',
    chatName: 'k8s服务支撑工程师',
    chatAvatar: '/avatars/03.png',
    messageId: 'm3-2',
    content: '已排查日志，发现大量 DB 超时，建议检查慢查询和连接数配置',
    timestamp: new Date('2025-10-28T09:15:00').getTime(),
  },
  {
    chatId: '3',
    chatName: 'k8s服务支撑工程师',
    chatAvatar: '/avatars/03.png',
    messageId: 'm3-3',
    content: '临时扩大副本数并开启熔断策略，观察服务恢复情况',
    timestamp: new Date('2025-10-28T09:16:00').getTime(),
  },
  {
    chatId: '4',
    chatName: 'ITSM服务台',
    chatAvatar: '/avatars/04.png',
    messageId: 'm4-1',
    content: '工单通知：机房 3A 交换机端口异常，已生成工单等待运维响应',
    timestamp: new Date('2025-10-30T11:20:00').getTime(),
  },
  {
    chatId: '4',
    chatName: 'ITSM服务台',
    chatAvatar: '/avatars/04.png',
    messageId: 'm4-2',
    content: '告警确认：/var 分区使用率 92%，建议清理日志或扩容',
    timestamp: new Date('2025-10-27T14:30:00').getTime(),
  },
  {
    chatId: '4',
    chatName: 'ITSM服务台',
    chatAvatar: '/avatars/04.png',
    messageId: 'm4-3',
    content: '工单更新：已完成磁盘清理，告警恢复；请继续监控下一周期',
    timestamp: new Date('2025-10-27T14:31:00').getTime(),
  }
];
