import type { ChatState, Message, WebChatConfig, LlmContextUsage, Locale } from '@webchat/core';

export interface ChatProps extends WebChatConfig {
  onStateChange?: (state: ChatState) => void;
  onMessageReceived?: (message: Message) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
  botAvatarUrl?: string;
  userAvatarUrl?: string;
  /** 界面语言；未传时按 webchat 默认（中文）渲染。 */
  locale?: Locale;
  agui?: {
    enabled?: boolean;
    debug?: boolean;
  };
  showFullscreenButton?: boolean;
  showClearButton?: boolean;
  conversationHistoryEnabled?: boolean;
  initialContextUsage?: LlmContextUsage | null;
  showHeader?: boolean;
  apiKey?: string;
  credentials?: RequestCredentials;
  requestHeaders?: Record<string, string>;
  initialMessages?: Message[];
  historyLoading?: boolean;
  wideLayout?: boolean;
  fullscreen?: boolean;
  onFullscreenChange?: (open: boolean) => void;
  onStreamingStop?: () => void;
  kickoffMessage?: string;
  onKickoffConsumed?: () => void;
  onCustomEvent?: (event: { type: 'CUSTOM'; name: string; value: unknown }) => void;
  /** @inheritdoc WebChatConfig.streamingTextBatching */
  streamingTextBatching?: WebChatConfig['streamingTextBatching'];
}
