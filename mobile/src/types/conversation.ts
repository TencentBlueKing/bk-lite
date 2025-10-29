export interface Message {
  id: string;
  content: string;
  timestamp: string;
  isOwn: boolean;
  type: 'text' | 'image' | 'audio';
}

export interface ChatMessage {
  id: string;
  content: string;
  sender: 'me' | 'other';
  timestamp: string;
}

export interface ChatInfo {
  id: string;
  name: string;
  avatar: string;
  status: 'online' | 'offline';
}

export interface ChatItem {
  id: string;
  name: string;
  avatar: string;
  lastMessage: string;
  time: string;
  website?: string;
  hasCall?: boolean;
  unread?: number;
}