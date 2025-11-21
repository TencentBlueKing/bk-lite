/**
 * AG-UI 协议事件类型定义
 */

// AI 运行状态事件
export interface RunStartedEvent {
    type: 'RUN_STARTED';
    timestamp: number;
    messageId: string;
}

export interface RunFinishedEvent {
    type: 'RUN_FINISHED';
    timestamp: number;
    messageId: string;
}

// 思考过程事件
export interface ThinkingStartEvent {
    type: 'THINKING_START';
    timestamp: number;
    messageId: string;
}

export interface ThinkingContentEvent {
    type: 'THINKING_CONTENT';
    timestamp: number;
    messageId: string;
    delta: string; // 块状文本
}

export interface ThinkingEndEvent {
    type: 'THINKING_END';
    timestamp: number;
    messageId: string;
}

// 文本消息事件
export interface TextMessageStartEvent {
    type: 'TEXT_MESSAGE_START';
    timestamp: number;
    messageId: string;
    role: 'assistant' | 'user';
}

export interface TextMessageContentEvent {
    type: 'TEXT_MESSAGE_CONTENT';
    timestamp: number;
    messageId: string;
    delta: string; // 块状文本
}

export interface TextMessageEndEvent {
    type: 'TEXT_MESSAGE_END';
    timestamp: number;
    messageId: string;
}

// 工具调用事件
export interface ToolCallEvent {
    type: 'TOOL_CALL';
    timestamp: number;
    parentMessageId: string;
    toolCallId: string;
    toolCallName: string;
}

export interface ToolCallArgsEvent {
    type: 'TOOL_CALL_ARGS';
    timestamp: number;
    toolCallId: string;
    delta: string;
}

export interface ToolCallEndEvent {
    type: 'TOOL_CALL_END';
    timestamp: number;
    toolCallId: string;
}

export interface ToolResultEvent {
    type: 'TOOL_RESULT';
    timestamp: number;
    messageId: string;
    toolCallId: string;
    result: any;
}

// 自定义事件类型
export interface CustomEvent {
    type: 'CUSTOM';
    name: 'render_component',
    value: {
        component: string,
        props: any
    }
}

// 联合类型
export type AGUIEvent =
    | RunStartedEvent
    | RunFinishedEvent
    | ThinkingStartEvent
    | ThinkingContentEvent
    | ThinkingEndEvent
    | TextMessageStartEvent
    | TextMessageContentEvent
    | TextMessageEndEvent
    | ToolCallEvent
    | ToolCallArgsEvent
    | ToolCallEndEvent
    | ToolResultEvent
    | CustomEvent;

// SSE 响应类型
export interface SSEResponse {
    data: string; // JSON 字符串形式的 AGUIEvent
}
