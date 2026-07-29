/**
 * Core type definitions for WebChat
 */

export type MessageType = 'text' | 'image' | 'markdown' | 'html' | 'file' | 'button' | 'multimodal';

export type ChatState = 'idle' | 'connecting' | 'connected' | 'chatting' | 'closed' | 'error';

export interface MessageContent {
  type: 'text' | 'image_url' | 'message';
  text?: string;
  message?: string;
  image_url?: string;
}

export interface Message {
  id: string;
  type: MessageType;
  content: string | MessageContent[];
  sender: 'user' | 'bot';
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface ChatSession {
  sessionId: string;
  userId?: string;
  messages: Message[];
  startTime: number;
  lastActivityTime: number;
  customData?: Record<string, unknown>;
}

export interface WebChatConfig {
  sseUrl?: string;
  /**
   * @deprecated Use `sseUrl` instead. When `sseUrl` is absent, this value is
   * normalized to `sseUrl` for compatibility.
   */
  socketUrl?: string;
  /**
   * @deprecated Include the complete endpoint path in `sseUrl`. This option is
   * retained for source compatibility but is not interpreted by WebChat.
   */
  socketPath?: string;
  customData?: Record<string, unknown>;
  theme?: 'light' | 'dark';
  title?: string;
  subtitle?: string;
  placeholder?: string;
  /**
   * @deprecated The UI uses one fetch stream and does not reconnect through
   * this option.
   */
  reconnectAttempts?: number;
  /**
   * @deprecated The UI uses one fetch stream and does not reconnect through
   * this option.
   */
  reconnectDelay?: number;
  /**
   * @deprecated WebChat uses SSE whenever `sseUrl` (or legacy `socketUrl`) is
   * configured.
   */
  enableSSE?: boolean;
  enableStorage?: boolean;
  storageKey?: string;
  /**
   * Opaque integration metadata. WebChat preserves this namespace but does not
   * include it in chat requests; request metadata belongs in `customData`.
   */
  extensions?: Record<string, unknown>;
}

export interface SSEMessage {
  event?: string;
  data: string;
  id?: string;
}

export interface ChatResponse {
  type: MessageType;
  content: string;
  metadata?: Record<string, unknown>;
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
  error: unknown;
  timestamp: number;
}

export type EventListener<T> = (event: T) => void;
