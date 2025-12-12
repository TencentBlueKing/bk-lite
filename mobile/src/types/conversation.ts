export interface ChatItem {
  id: string;
  name: string;
  avatar: string;
  lastMessage?: string;
  time?: string;
  hasCall?: boolean;
  website?: string;
  unread?: number;
}

export interface ChatMessage {
  id: string;
  chatId: string;
  sender: 'user' | 'bot';
  content: string;
  timestamp: number;
}
export interface sessionsItem {
  bot_id: number;
  session_id: string;
  title: string;
}
export interface ChatInfo {
  id: string;
  name: string;
  avatar: string;
}

export interface ToolCall {
  id: string;
  name: string;
  args: string;
  result?: any;
  status: 'executing' | 'completed' | 'fail';
}

export interface ContentPart {
  type: 'text' | 'component' | 'tool_call';
  content?: string | React.ReactNode;
  component?: {
    name: string;
    props: any;
  }; // 组件配置
  toolCall?: ToolCall; // 工具调用信息
  segmentIndex?: number; // 分段索引
}

export interface Message {
  id: string;
  message: string | React.ReactNode | null | { text: string; suggestions: string[] };
  status: 'local' | 'ai' | 'thinking' | 'loading' | 'success' | 'ended' | 'history';
  timestamp: number;
  thinking?: string;
  userInput?: string;
  isWelcome?: boolean;
  toolCalls?: ToolCall[];
  customComponent?: {
    component: string;
    props: any;
  }; // 自定义组件配置
  contentParts?: ContentPart[]; // 按顺序的内容片段(文本和组件)
}

/**
 * AI 对话事件类型
 */
export interface AIChatEvent {
  type: 'RUN_STARTED' | 'THINKING_START' | 'THINKING_CONTENT' | 'THINKING_END' |
  'TEXT_MESSAGE_START' | 'TEXT_MESSAGE_CONTENT' | 'TEXT_MESSAGE_END' |
  'TOOL_CALL_START' | 'TOOL_CALL_ARGS' | 'TOOL_CALL_END' | 'TOOL_CALL_RESULT' |
  'CUSTOM' | 'RUN_FINISHED';
  timestamp?: number;
  messageId?: string;
  runId?: string;
  threadId?: string;
  delta?: string;
  msg?: string;
  toolCallId?: string;
  toolCallName?: string;
  result?: any;
  name?: string;
  value?: any;
  content?: string;
}