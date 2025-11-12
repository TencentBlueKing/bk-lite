import { UserInfo } from '@/types/user';
import { ChatItem, ChatMessage } from '@/types/conversation';

// 重新导出类型以保持向后兼容
export type { ChatItem, ChatMessage, UserInfo };

export const mockChatData: ChatItem[] = [
  {
    id: '1',
    name: 'Mary (英式口语搭子)',
    avatar: '/avatars/01.svg',
    lastMessage: '嗨，我是你的新朋友Mary！初次见面很开心...',
    time: '14:56',
    website: '',
  },
  {
    id: '2',
    name: 'Mia (美式口语搭子)',
    avatar: '/avatars/02.svg',
    lastMessage: 'OMG, hi there! I\'m like, so stoked to chat...',
    time: '13:45',
    hasCall: true,
  },
  {
    id: '3',
    name: 'Jake (美式口语搭子)',
    avatar: '/avatars/05.svg',
    lastMessage: 'Yo, Jake here! How\'s it going? Let\'s hang...',
    time: '12:30',
    hasCall: true,
  },
  {
    id: '4',
    name: '英语外教 Owen',
    avatar: '/avatars/04.svg',
    lastMessage: 'Hey there! How\'s your day going?',
    time: '11:20',
  },
  {
    id: '5',
    name: '华泰股市助手',
    avatar: '/avatars/05.svg',
    lastMessage: '新手炒股太难？有哪些实用的选股技巧和避...',
    time: '10:15',
  },
  {
    id: '6',
    name: '中英翻译',
    avatar: '/avatars/01.svg',
    lastMessage: '我擅长中英文互翻，请以"翻译："xxx"的格...',
    time: '昨天',
  },
  {
    id: '7',
    name: 'Zoe (英式口语搭子)',
    avatar: '/avatars/03.svg',
    lastMessage: 'Hi! I\'m Zoe! Love a bit of celebrity gossip...',
    time: '昨天',
    hasCall: true,
  },
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
        id: 47,
        team_name: ['Default'],
        permissions: ['View', 'Operate'],
        created_by: 'admin',
        updated_by: 'admin',
        domain: 'domain.com',
        updated_by_domain: 'domain.com',
        name: 'weops小助手',
        introduction: '这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手这是weops小助手',
        team: [1],
        channels: [],
        enable_bot_domain: false,
        bot_domain: null,
        enable_node_port: false,
        node_port: 5005,
        online: false,
        enable_ssl: false,
        api_token: '',
        replica_count: 1,
        bot_type: 3,
        rasa_model: null,
        llm_skills: [],
      },
      {
        id: 46,
        team_name: ['Default'],
        permissions: ['View', 'Operate'],
        created_by: 'admin',
        updated_by: 'admin',
        domain: 'domain.com',
        updated_by_domain: 'domain.com',
        name: 'pilottest',
        introduction: 'aaaaaaa',
        team: [1],
        channels: [103],
        enable_bot_domain: false,
        bot_domain: null,
        enable_node_port: true,
        node_port: 58080,
        online: false,
        enable_ssl: false,
        api_token: '',
        replica_count: 1,
        bot_type: 1,
        rasa_model: 1,
        llm_skills: [4323],
      },
      {
        id: 40,
        team_name: ['Default'],
        permissions: ['View', 'Operate'],
        created_by: 'admin',
        updated_by: 'admin',
        domain: 'domain.com',
        updated_by_domain: 'domain.com',
        name: '333',
        introduction: '3333',
        team: [1],
        channels: [91],
        enable_bot_domain: false,
        bot_domain: null,
        enable_node_port: true,
        node_port: 58080,
        online: false,
        enable_ssl: false,
        api_token: '',
        replica_count: 1,
        bot_type: 1,
        rasa_model: 1,
        llm_skills: [4323],
      },
      {
        id: 36,
        team_name: ['Default'],
        permissions: ['View', 'Operate'],
        created_by: 'admin',
        updated_by: 'admin',
        domain: 'domain.com',
        updated_by_domain: 'domain.com',
        name: 'BKLite Flow',
        introduction: 'BKLite Flow',
        team: [1],
        channels: [],
        enable_bot_domain: false,
        bot_domain: null,
        enable_node_port: false,
        node_port: 5005,
        online: true,
        enable_ssl: false,
        api_token: '476b4638ffcfc92f98ce6f3201c451dd7e76bc0f82884cdf850669ba3d731a63',
        replica_count: 1,
        bot_type: 3,
        rasa_model: null,
        llm_skills: [],
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
  // Mary (英式口语搭子) 的消息
  {
    chatId: '1',
    chatName: 'Mary (英式口语搭子)',
    chatAvatar: '/avatars/01.svg',
    messageId: 'm1-1',
    content: '嗨，我是你的新朋友Mary！初次见面很开心，咱们可以聊聊天气、美食或者任何你感兴趣的话题。把啦啦啦啦啦啊啊啊',
    timestamp: new Date('2025-10-30T14:56:00').getTime(),
  },
  {
    chatId: '1',
    chatName: 'Mary (英式口语搭子)',
    chatAvatar: '/avatars/01.svg',
    messageId: 'm1-2',
    content: 'How do you think about British accent?',
    timestamp: new Date('2025-10-30T10:30:00').getTime(),
  },
  {
    chatId: '1',
    chatName: 'Mary (英式口语搭子)',
    chatAvatar: '/avatars/01.svg',
    messageId: 'm1-3',
    content: '我觉得英式发音听起来特别优雅',
    timestamp: new Date('2025-10-30T10:31:00').getTime(),
  },

  // Mia (美式口语搭子) 的消息
  {
    chatId: '2',
    chatName: 'Mia (美式口语搭子)',
    chatAvatar: '/avatars/02.svg',
    messageId: 'm2-1',
    content: 'OMG, hi there! I\'m like, so stoked to chat with you! Let\'s talk about movies, music, or whatever!',
    timestamp: new Date('2025-10-30T13:45:00').getTime(),
  },
  {
    chatId: '2',
    chatName: 'Mia (美式口语搭子)',
    chatAvatar: '/avatars/02.svg',
    messageId: 'm2-2',
    content: 'Have you seen the latest Marvel movie?',
    timestamp: new Date('2025-10-29T16:20:00').getTime(),
  },
  {
    chatId: '2',
    chatName: 'Mia (美式口语搭子)',
    chatAvatar: '/avatars/02.svg',
    messageId: 'm2-3',
    content: '还没看呢，最近比较忙',
    timestamp: new Date('2025-10-29T16:21:00').getTime(),
  },

  // Jake (美式口语搭子) 的消息
  {
    chatId: '3',
    chatName: 'Jake (美式口语搭子)',
    chatAvatar: '/avatars/05.svg',
    messageId: 'm3-1',
    content: 'Yo, Jake here! How\'s it going? Let\'s hang out and practice some casual American English!',
    timestamp: new Date('2025-10-30T12:30:00').getTime(),
  },
  {
    chatId: '3',
    chatName: 'Jake (美式口语搭子)',
    chatAvatar: '/avatars/05.svg',
    messageId: 'm3-2',
    content: 'What do you usually do on weekends?',
    timestamp: new Date('2025-10-28T09:15:00').getTime(),
  },
  {
    chatId: '3',
    chatName: 'Jake (美式口语搭子)',
    chatAvatar: '/avatars/05.svg',
    messageId: 'm3-3',
    content: '通常会去健身房或者看电影',
    timestamp: new Date('2025-10-28T09:16:00').getTime(),
  },

  // 英语外教 Owen 的消息
  {
    chatId: '4',
    chatName: '英语外教 Owen',
    chatAvatar: '/avatars/04.svg',
    messageId: 'm4-1',
    content: 'Hey there! How\'s your day going? Ready for today\'s English lesson?',
    timestamp: new Date('2025-10-30T11:20:00').getTime(),
  },
  {
    chatId: '4',
    chatName: '英语外教 Owen',
    chatAvatar: '/avatars/04.svg',
    messageId: 'm4-2',
    content: 'Could you help me with grammar?',
    timestamp: new Date('2025-10-27T14:30:00').getTime(),
  },
  {
    chatId: '4',
    chatName: '英语外教 Owen',
    chatAvatar: '/avatars/04.svg',
    messageId: 'm4-3',
    content: 'Of course! What specific grammar points would you like to review?',
    timestamp: new Date('2025-10-27T14:31:00').getTime(),
  }
]