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

export interface PageContextSection {
  id?: string;
  label?: string;
  content: string;
  priority?: number;
}

export interface PageContextImage {
  caption?: string;
  dataUrl: string;
}

export interface PageContext {
  url?: string;
  app?: string;
  title?: string;
  sections?: PageContextSection[];
  images?: PageContextImage[];
}

export type CollectPageContext = (hint?: { message?: string }) => Promise<PageContext | null | undefined>;

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
   * Stable owner + endpoint scope for persisted local sessions. When set,
   * WebChat stores under an isolated v2 key. Do not use a rotating access token.
   */
  storageScope?: string;
  /** Coalesce streaming text per animation frame; set false for immediate rollback. */
  streamingTextBatching?: boolean;
  /** Maximum images accepted for one unsent message. Defaults to 4. */
  maxImageCount?: number;
  /** Maximum original image bytes accepted for one unsent message. Defaults to 16 MiB. */
  maxTotalImageBytes?: number;
  /** Maximum simultaneous FileReader operations. Defaults to 2. */
  imageReadConcurrency?: number;
  /** Maximum decoded pixels accepted for one image. Defaults to 16 Mi pixels. */
  maxImagePixels?: number;
  /** Maximum decoded pixels accepted for one unsent message. Defaults to 32 Mi pixels. */
  maxTotalImagePixels?: number;
  /** Preview formats whose dimensions cannot be inspected; defaults to false. */
  allowUnknownImagePreview?: boolean;
  /**
   * Opaque integration metadata. WebChat preserves this namespace but does not
   * include it in chat requests; request metadata belongs in `customData`.
   */
  extensions?: Record<string, unknown>;
  /**
   * Host callback: collect current page snapshot immediately before send.
   * When provided, WebChat calls this on every send; return null when no page context applies.
   */
  collectContext?: CollectPageContext;
  /**
   * Host-injected platform assistant contract. When present with required URLs,
   * WebChat runs in platform mode and ignores top-level `sseUrl`.
   */
  platform?: PlatformContract;
}

/** URL templates may include `{channelId}` and `{sessionId}`. */
export interface PlatformContract {
  applicationsUrl: string;
  sessionsUrl: string;
  messagesUrl: string;
  /** POST JSON `{ session_id }` to delete one persisted conversation. */
  deleteSessionUrl?: string;
  chatUrlTemplate: string;
  interruptUrl?: string;
  approvalUrl?: string;
  choiceUrl?: string;
  credentials?: RequestCredentials;
  headers?: Record<string, string>;
  storageKey?: string;
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
