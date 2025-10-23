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
