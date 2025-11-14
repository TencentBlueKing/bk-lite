import { UserInfo } from '@/types/user';
import { ChatItem, ChatMessage } from '@/types/conversation';

// 重新导出类型以保持向后兼容
export type { ChatItem, ChatMessage, UserInfo };

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
    name: 'k8s服务支撑工程师',
    avatar: '/avatars/03.png',
    lastMessage: 'API 响应码 500 增加，可能是后端服务超时或依赖异常',
    time: '12:30',
    hasCall: true,
  },
  {
    id: '4',
    name: 'itsm事件管理员',
    avatar: '/avatars/04.png',
    lastMessage: '工单#1234：磁盘空间告警，/var 分区剩余 < 10%',
    time: '11:20',
  }
];

// 虚拟工作台数据（用于后端无数据时回退）
export const mockWorkbenchData = {
  result: true,
  code: '20000',
  message: 'success',
  data: {
    count: 4,
    items: [
      {
        id: 1,
        name: 'k8s平台监控工程师',
        introduction: '专注 K8s 集群智能监控，自动采集指标、分析性能瓶颈，实时预警故障并辅助排查，保障平台稳定高效运行。',
        online: false,
        bot_type: 3,
        avatar: '/avatars/01.png',
      },
      {
        id: 2,
        name: 'K8s平台架构师',
        introduction: '智能体 K8s 平台架构师，负责集群架构设计与优化，推动智能化部署、资源调度及高可用方案，保障平台弹性与高效。',
        online: false,
        bot_type: 1,
        avatar: '/avatars/02.png',
      },
      {
        id: 3,
        name: 'K8s服务支撑工程师',
        introduction: '智能体 K8s 服务支撑工程师，提供集群部署运维、故障排查与技术支持，协同团队优化流程，保障云原生服务稳定高效响应需求。',
        online: false,
        bot_type: 1,
        avatar: '/avatars/03.png',
      },
      {
        id: 4,
        name: 'ITSM服务台',
        introduction: '智能体 ITSM服务台，负责事件全生命周期智能管控，快速响应、分级处置、跟踪闭环，优化流程并保障 IT 服务稳定合规。',
        online: true,
        bot_type: 3,
        avatar: '/avatars/04.png',
      },
    ],
  },
};

// Mock 账户信息数据
export const mockAccountInfo = {
  username: 'admin',
  displayName: '张三',
  email: 'zhangsan@example.com',
  timezone: 'Asia/Shanghai',
  language: 'zh',
  organizations: ['运维部', '开发组', '测试团队'],
  roles: ['系统管理员', '运维工程师', '项目负责人', '技术支持', '数据分析师', '产品经理', '架构师', '安全审计员', '运维专家'],
  userType: '普通用户',
};

const now = new Date();

export const mockChatHistory = [
  {
    id: 1,
    chatHistory: [
      {
        id: '1',
        role: 'local' as const,
        content: '你好，请帮我介绍一下蓝鲸平台的主要功能',
        timestamp: new Date(now.getTime() - 30 * 60 * 1000).getTime(), // 30分钟前
      },
      {
        id: '2',
        role: 'ai' as const,
        content: '您好！蓝鲸平台是一个 AI 原生的轻量化运维平台，主要功能包括：\n\n1. **智能运维**：通过 AI 技术实现自动化运维管理\n2. **多渠道接入**：支持 Web、移动端等多种访问方式\n3. **智能对话**：提供自然语言交互能力\n4. **工作台管理**：集成多种运维工具和应用\n\n有什么具体想了解的功能吗？',
        timestamp: new Date(now.getTime() - 30 * 60 * 1000 + 2000).getTime(), // 30分钟前+2秒
        thinking: '正在理解您的问题...\n\n1. **语义分析**：识别"蓝鲸平台"和"主要功能"关键词\n2. **检索知识库**：查找平台核心特性\n3. **组织答案**：按功能模块分类\n4. **优化表达**：使用清晰的列表格式',
      },
      {
        id: '3',
        role: 'local' as const,
        content: '能展示一个表格吗？',
        timestamp: new Date(now.getTime() - 10 * 60 * 1000).getTime(), // 10分钟前（间隔20分钟，应该显示时间）
      },
      {
        id: '4',
        role: 'ai' as const,
        content: `## 服务器状态对比表格

这是一个服务器状态对比表格：

| 服务器 | 状态 | CPU | 内存 |
|--------|------|-----|------|
| Server-01 | ✅ 正常 | 45% | 62% |
| Server-02 | ❌ 异常 | 89% | 95% |
| Server-03 | ✅ 正常 | 32% | 58% |

### 分析说明

- **Server-01**: 运行正常，资源使用率在合理范围内
- **Server-02**: ⚠️ **需要关注**，CPU 和内存使用率过高，建议立即检查
- **Server-03**: 运行正常，负载较低

> 💡 提示：Server-02 的高负载可能影响系统稳定性，建议尽快处理。`,
        timestamp: new Date(now.getTime() - 10 * 60 * 1000 + 1500).getTime(), // 10分钟前+1.5秒
        thinking: '正在分析您的需求...\n\n1. **识别关键词**："表格"相关请求\n2. **检索数据源**：查询服务器状态数据\n3. **格式化输出**：生成 Markdown 表格格式\n4. **添加分析**：补充状态说明和建议',
      },
    ]
  }
]

// Mock 聊天记录数据（用于搜索）
export interface ChatMessageRecord {
  chatId: string;
  chatName: string;
  chatAvatar: string;
  messageId: string;
  content: string;
  timestamp: number;
}

export const mockChatMessages: ChatMessageRecord[] = [
  // k8s平台监控工程师 的消息
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

  // k8s平台架构师 的消息
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

  // k8s服务支撑工程师 的消息
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

  // ITSM服务台 的消息
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
]