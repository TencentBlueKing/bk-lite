/**
 * Core type definitions for WebChat
 */

export type MessageType = 'text' | 'image' | 'markdown' | 'html' | 'file' | 'button';

export type ChatState = 'idle' | 'connecting' | 'connected' | 'chatting' | 'closed' | 'error';

export interface Message {
  id: string;
  type: MessageType;
  content: string;
  sender: 'user' | 'bot';
  timestamp: number;
  metadata?: Record<string, any>;
}

export interface ChatSession {
  sessionId: string;
  userId?: string;
  messages: Message[];
  startTime: number;
  lastActivityTime: number;
  customData?: Record<string, any>;
}

export interface WebChatConfig {
  sseUrl?: string;
  socketUrl?: string; // Deprecated: use sseUrl instead
  socketPath?: string;
  customData?: Record<string, any>;
  theme?: 'light' | 'dark';
  title?: string;
  subtitle?: string;
  placeholder?: string;
  reconnectAttempts?: number;
  reconnectDelay?: number;
  enableSSE?: boolean;
  enableStorage?: boolean;
  storageKey?: string;
  [key: string]: any;
}

export interface SSEMessage {
  event?: string;
  data: string;
  id?: string;
}

export interface ChatResponse {
  type: MessageType;
  content: string;
  metadata?: Record<string, any>;
}

export interface StateChangeEvent {
  from: ChatState;
  to: ChatState;
  timestamp: number;
}

export interface MessageEvent {
  message: Message;
  timestamp: number;
}

export interface ErrorEvent {
  error: Error;
  timestamp: number;
}

export type EventListener<T> = (event: T) => void;
