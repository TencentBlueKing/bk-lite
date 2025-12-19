'use client';

import React, { createContext, useContext, useSyncExternalStore } from 'react';
import { aiChatStream } from '@/api/bot';
import type { Message, ToolCall, MessageContentItem } from '@/types/conversation';

/**
 * 单个会话的状态
 */
export interface SessionState {
    messages: Message[];
    thinkingExpanded: Record<string, boolean>;
    thinkingTypingText: Record<string, string>;
    messageMarkdown: Map<string, string>;
    isAIRunning: boolean;
    isNewConversation: boolean;  // 是否为新对话（用于判断发送消息后是否需要刷新对话列表）
    lastUpdated: number;
}

/**
 * 流式请求的控制器
 */
interface StreamController {
    abort: () => void;
    isRunning: boolean;
}

/**
 * 渲染函数类型
 */
type RenderMarkdownFn = (text: string) => React.ReactNode;

/**
 * 全局会话管理器 - 核心类
 * 独立于 React 组件生命周期，管理所有会话的状态和后台流式请求
 * 
 * 性能优化：
 * - 使用 LRU 策略，只缓存最近访问的 N 个会话
 * - 正在运行 AI 的会话受保护，不会被清理
 * - 超过最大数量时自动清理最老的非活跃会话
 */
class ConversationManager {
    private sessions: Map<string, SessionState> = new Map();
    private streamControllers: Map<string, StreamController> = new Map();
    private listeners: Set<() => void> = new Set();
    // 缓存 runningSessionIds，避免 useSyncExternalStore 无限循环
    private _runningSessionIdsCache: string[] = [];

    // LRU 缓存配置
    private readonly MAX_CACHED_SESSIONS = 10;  // 最大缓存会话数
    private accessOrder: string[] = [];  // 记录访问顺序，最近访问的在末尾

    /**
     * 更新会话访问顺序（LRU）
     */
    private touchSession(sessionId: string): void {
        // 从当前位置移除
        const index = this.accessOrder.indexOf(sessionId);
        if (index > -1) {
            this.accessOrder.splice(index, 1);
        }
        // 添加到末尾（最近访问）
        this.accessOrder.push(sessionId);
    }

    /**
     * 清理过期的会话（LRU 策略）
     * 保留：正在运行 AI 的会话 + 最近访问的 N 个会话
     */
    private cleanupSessions(): void {
        // 如果会话数量未超过限制，不需要清理
        if (this.sessions.size <= this.MAX_CACHED_SESSIONS) {
            return;
        }

        // 获取所有正在运行的会话 ID
        const runningIds = new Set<string>();
        this.sessions.forEach((state, id) => {
            if (state.isAIRunning) {
                runningIds.add(id);
            }
        });

        // 计算需要清理的数量
        const targetSize = this.MAX_CACHED_SESSIONS;
        let currentSize = this.sessions.size;

        // 从最老的开始清理（accessOrder 开头）
        const toRemove: string[] = [];
        for (const sessionId of this.accessOrder) {
            if (currentSize <= targetSize) break;

            // 跳过正在运行的会话
            if (runningIds.has(sessionId)) continue;

            toRemove.push(sessionId);
            currentSize--;
        }

        // 执行清理
        for (const sessionId of toRemove) {
            this.sessions.delete(sessionId);
            const orderIndex = this.accessOrder.indexOf(sessionId);
            if (orderIndex > -1) {
                this.accessOrder.splice(orderIndex, 1);
            }
        }
    }

    /**
     * 获取缓存统计信息（调试用）
     */
    getCacheStats(): { total: number; running: number; maxSize: number } {
        return {
            total: this.sessions.size,
            running: this._runningSessionIdsCache.length,
            maxSize: this.MAX_CACHED_SESSIONS,
        };
    }

    /**
     * 获取所有正在运行 AI 的会话 ID（返回缓存的引用）
     */
    getRunningSessionIds(): string[] {
        return this._runningSessionIdsCache;
    }

    /**
     * 更新 runningSessionIds 缓存
     */
    private updateRunningSessionIdsCache(): void {
        const running: string[] = [];
        this.sessions.forEach((state, sessionId) => {
            if (state.isAIRunning) {
                running.push(sessionId);
            }
        });
        // 只有内容变化时才更新引用
        const oldIds = this._runningSessionIdsCache;
        if (running.length !== oldIds.length || !running.every((id, i) => id === oldIds[i])) {
            this._runningSessionIdsCache = running;
        }
    }

    /**
     * 检查指定会话是否正在运行 AI
     */
    isSessionRunning(sessionId: string): boolean {
        return this.sessions.get(sessionId)?.isAIRunning || false;
    }

    /**
     * 获取会话状态
     */
    getSessionState(sessionId: string): SessionState | undefined {
        const state = this.sessions.get(sessionId);
        if (state) {
            // 更新访问顺序（LRU）
            this.touchSession(sessionId);
        }
        return state;
    }

    /**
     * 初始化会话状态（如果不存在）
     */
    initSession(sessionId: string): SessionState {
        if (!this.sessions.has(sessionId)) {
            const newState: SessionState = {
                messages: [],
                thinkingExpanded: {},
                thinkingTypingText: {},
                messageMarkdown: new Map(),
                isAIRunning: false,
                isNewConversation: false,
                lastUpdated: Date.now(),
            };
            this.sessions.set(sessionId, newState);

            // 清理过期会话（LRU）
            this.cleanupSessions();
        }
        // 更新访问顺序
        this.touchSession(sessionId);
        return this.sessions.get(sessionId)!;
    }

    /**
     * 设置新对话标记
     */
    setNewConversation(sessionId: string, isNew: boolean): void {
        this.updateSession(sessionId, (state) => ({
            ...state,
            isNewConversation: isNew,
        }));
    }

    /**
     * 获取新对话标记
     */
    isNewConversation(sessionId: string): boolean {
        return this.sessions.get(sessionId)?.isNewConversation || false;
    }

    /**
     * 更新会话状态
     */
    updateSession(sessionId: string, updater: (state: SessionState) => SessionState): void {
        const current = this.sessions.get(sessionId);
        if (current) {
            const newState = updater(current);
            newState.lastUpdated = Date.now();
            this.sessions.set(sessionId, newState);
            this.notifyListeners();
        }
    }

    /**
     * 设置会话消息
     */
    setMessages(sessionId: string, messages: Message[]): void {
        this.updateSession(sessionId, (state) => ({
            ...state,
            messages,
        }));
    }

    /**
     * 更新会话消息（使用更新函数）
     */
    updateMessages(sessionId: string, updater: (messages: Message[]) => Message[]): void {
        this.updateSession(sessionId, (state) => ({
            ...state,
            messages: updater(state.messages),
        }));
    }

    /**
     * 设置思考过程展开状态
     */
    setThinkingExpanded(sessionId: string, expanded: Record<string, boolean>): void {
        this.updateSession(sessionId, (state) => ({
            ...state,
            thinkingExpanded: expanded,
        }));
    }

    /**
     * 更新思考过程展开状态
     */
    updateThinkingExpanded(sessionId: string, msgId: string, expanded: boolean): void {
        this.updateSession(sessionId, (state) => ({
            ...state,
            thinkingExpanded: { ...state.thinkingExpanded, [msgId]: expanded },
        }));
    }

    /**
     * 设置思考过程文本
     */
    setThinkingTypingText(sessionId: string, text: Record<string, string>): void {
        this.updateSession(sessionId, (state) => ({
            ...state,
            thinkingTypingText: text,
        }));
    }

    /**
     * 更新思考过程文本
     */
    updateThinkingTypingText(sessionId: string, msgId: string, text: string): void {
        this.updateSession(sessionId, (state) => ({
            ...state,
            thinkingTypingText: { ...state.thinkingTypingText, [msgId]: text },
        }));
    }

    /**
     * 设置 AI 运行状态
     */
    setAIRunning(sessionId: string, running: boolean): void {
        this.updateSession(sessionId, (state) => ({
            ...state,
            isAIRunning: running,
        }));
    }

    /**
     * 保存 Markdown 原文
     */
    setMessageMarkdown(sessionId: string, msgId: string, markdown: string): void {
        const state = this.sessions.get(sessionId);
        if (state) {
            state.messageMarkdown.set(msgId, markdown);
        }
    }

    /**
     * 获取 Markdown 原文
     */
    getMessageMarkdown(sessionId: string, msgId: string): string | undefined {
        return this.sessions.get(sessionId)?.messageMarkdown.get(msgId);
    }

    /**
     * 清除会话状态
     */
    clearSession(sessionId: string): void {
        // 先取消正在进行的流式请求
        this.abortStream(sessionId);
        this.sessions.delete(sessionId);
        this.notifyListeners();
    }

    /**
     * 取消流式请求
     */
    abortStream(sessionId: string): void {
        const controller = this.streamControllers.get(sessionId);
        if (controller) {
            controller.abort();
            this.streamControllers.delete(sessionId);
        }
    }

    /**
     * 订阅状态变化
     */
    subscribe(listener: () => void): () => void {
        this.listeners.add(listener);
        return () => {
            this.listeners.delete(listener);
        };
    }

    /**
     * 通知所有监听者
     */
    private notifyListeners(): void {
        // 更新 runningSessionIds 缓存
        this.updateRunningSessionIdsCache();
        this.listeners.forEach((listener) => listener());
    }

    /**
     * 获取快照（用于 useSyncExternalStore）
     */
    getSnapshot(): Map<string, SessionState> {
        return this.sessions;
    }

    /**
     * 发送消息并启动 AI 响应流
     * @param sessionId 会话 ID
     * @param bot Bot ID
     * @param nodeId Node ID
     * @param userMessage 用户消息
     * @param renderMarkdown Markdown 渲染函数
     * @param errorMessage 错误提示消息
     * @param addUserMessage 是否添加用户消息（文件消息场景不需要）
     */
    async startAIResponse(
        sessionId: string,
        bot: number,
        nodeId: string,
        userMessage: string | MessageContentItem[],
        renderMarkdown: RenderMarkdownFn,
        errorMessage: string = '响应异常，请稍后再试',
        addUserMessage: boolean = true
    ): Promise<void> {
        // 初始化会话
        this.initSession(sessionId);

        const userMessageTimestamp = Date.now();
        const userMsgId = `user-${userMessageTimestamp}`;
        const aiMsgId = `ai-${userMessageTimestamp}`;

        // 添加用户消息和 AI loading 消息
        this.setAIRunning(sessionId, true);

        if (addUserMessage && typeof userMessage === 'string') {
            this.setMessageMarkdown(sessionId, userMsgId, userMessage);
            this.updateMessages(sessionId, (prev) => [
                ...prev,
                {
                    id: userMsgId,
                    message: renderMarkdown(userMessage),
                    status: 'local',
                    timestamp: userMessageTimestamp,
                },
                {
                    id: aiMsgId,
                    message: null,
                    status: 'loading',
                    timestamp: Date.now(),
                    thinking: '',
                    userInput: userMessage,
                    toolCalls: [],
                }
            ]);
        } else {
            // 只添加 AI loading 消息
            this.updateMessages(sessionId, (prev) => [
                ...prev,
                {
                    id: aiMsgId,
                    message: null,
                    status: 'loading',
                    timestamp: Date.now(),
                    thinking: '',
                    userInput: userMessage,
                    toolCalls: [],
                }
            ]);
        }

        // 创建取消控制器
        let aborted = false;
        const controller: StreamController = {
            abort: () => { aborted = true; },
            isRunning: true,
        };
        this.streamControllers.set(sessionId, controller);

        // 启动流式处理
        await this.handleAGUIEventStream(
            sessionId,
            bot,
            nodeId,
            userMessage,
            aiMsgId,
            renderMarkdown,
            errorMessage,
            () => aborted
        );

        // 清理控制器
        this.streamControllers.delete(sessionId);
    }

    /**
     * 处理 AG-UI 事件流
     */
    private async handleAGUIEventStream(
        sessionId: string,
        bot: number,
        nodeId: string,
        userMessage: string | MessageContentItem[],
        aiMsgId: string,
        renderMarkdown: RenderMarkdownFn,
        errorMessage: string,
        isAborted: () => boolean
    ): Promise<void> {
        let thinkingAccumulated = '';
        let currentTextSegmentIndex = 0;
        let messageAccumulated = '';
        let totalMessageAccumulated = '';
        const toolArgsAccumulated: Record<string, string> = {};

        try {
            const eventStream = aiChatStream(bot, nodeId, userMessage, sessionId);

            for await (const event of eventStream) {
                // 检查是否已取消
                if (isAborted()) {
                    return;
                }

                switch (event.type) {
                    case 'RUN_STARTED':
                        this.updateMessages(sessionId, (prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, timestamp: event.timestamp || msg.timestamp }
                                    : msg
                            )
                        );
                        break;

                    case 'THINKING_START':
                        this.updateMessages(sessionId, (prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, status: 'thinking' }
                                    : msg
                            )
                        );
                        this.updateThinkingExpanded(sessionId, aiMsgId, true);
                        break;

                    case 'THINKING_CONTENT':
                        thinkingAccumulated += event.delta || '';
                        this.updateThinkingTypingText(sessionId, aiMsgId, thinkingAccumulated);
                        this.updateMessages(sessionId, (prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, thinking: thinkingAccumulated }
                                    : msg
                            )
                        );
                        break;

                    case 'THINKING_END':
                        this.updateMessages(sessionId, (prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, status: 'loading' }
                                    : msg
                            )
                        );
                        break;

                    case 'TOOL_CALL_START':
                        this.updateMessages(sessionId, (prev) =>
                            prev.map((msg) => {
                                if (msg.id === aiMsgId) {
                                    const newToolCall: ToolCall = {
                                        id: event.toolCallId || `tool-${Date.now()}`,
                                        name: event.toolCallName || 'Unknown Tool',
                                        args: '',
                                        status: 'executing',
                                    };
                                    const parts = msg.contentParts || [];
                                    return {
                                        ...msg,
                                        contentParts: [...parts, {
                                            type: 'tool_call' as const,
                                            toolCall: newToolCall
                                        }],
                                        status: 'success'
                                    };
                                }
                                return msg;
                            })
                        );
                        if (event.toolCallId) {
                            toolArgsAccumulated[event.toolCallId] = '';
                        }
                        break;

                    case 'TOOL_CALL_ARGS':
                        if (event.toolCallId) {
                            const toolCallId = event.toolCallId;
                            toolArgsAccumulated[toolCallId] = (toolArgsAccumulated[toolCallId] || '') + (event.delta || '');
                            this.updateMessages(sessionId, (prev) =>
                                prev.map((msg) => {
                                    if (msg.id === aiMsgId) {
                                        const updatedParts = msg.contentParts?.map(part => {
                                            if (part.type === 'tool_call' && part.toolCall?.id === toolCallId) {
                                                return {
                                                    ...part,
                                                    toolCall: {
                                                        id: part.toolCall.id,
                                                        name: part.toolCall.name,
                                                        args: toolArgsAccumulated[toolCallId],
                                                        result: part.toolCall.result,
                                                        status: part.toolCall.status,
                                                    }
                                                };
                                            }
                                            return part;
                                        });
                                        return {
                                            ...msg,
                                            contentParts: updatedParts,
                                        };
                                    }
                                    return msg;
                                })
                            );
                        }
                        break;

                    case 'TOOL_CALL_END':
                        break;

                    case 'TOOL_CALL_RESULT':
                        if (event.toolCallId) {
                            const toolCallId = event.toolCallId;
                            this.updateMessages(sessionId, (prev) =>
                                prev.map((msg) => {
                                    if (msg.id === aiMsgId) {
                                        const updatedParts = msg.contentParts?.map(part => {
                                            if (part.type === 'tool_call' && part.toolCall?.id === toolCallId) {
                                                return {
                                                    ...part,
                                                    toolCall: {
                                                        id: part.toolCall.id,
                                                        name: part.toolCall.name,
                                                        args: part.toolCall.args,
                                                        result: event.content,
                                                        status: 'completed' as const,
                                                    }
                                                };
                                            }
                                            return part;
                                        });
                                        return {
                                            ...msg,
                                            contentParts: updatedParts,
                                        };
                                    }
                                    return msg;
                                })
                            );
                        }
                        break;

                    case 'TEXT_MESSAGE_START':
                        messageAccumulated = '';
                        currentTextSegmentIndex++;
                        break;

                    case 'TEXT_MESSAGE_CONTENT':
                        const textDelta = event.delta || event.msg || '';
                        messageAccumulated += textDelta;
                        totalMessageAccumulated += textDelta;

                        const renderedContent = renderMarkdown(messageAccumulated);

                        this.updateMessages(sessionId, (prev) =>
                            prev.map((msg) => {
                                if (msg.id === aiMsgId) {
                                    const parts = msg.contentParts || [];
                                    const existingTextPartIndex = parts.findIndex(p =>
                                        p.type === 'text' && p.segmentIndex === currentTextSegmentIndex
                                    );

                                    if (existingTextPartIndex >= 0) {
                                        const updatedParts = [...parts];
                                        updatedParts[existingTextPartIndex] = {
                                            type: 'text' as const,
                                            content: renderedContent,
                                            segmentIndex: currentTextSegmentIndex
                                        };
                                        return {
                                            ...msg,
                                            status: 'success',
                                            contentParts: updatedParts
                                        };
                                    } else {
                                        return {
                                            ...msg,
                                            status: 'success',
                                            contentParts: [...parts, {
                                                type: 'text' as const,
                                                content: renderedContent,
                                                segmentIndex: currentTextSegmentIndex
                                            }]
                                        };
                                    }
                                }
                                return msg;
                            })
                        );
                        break;

                    case 'TEXT_MESSAGE_END':
                        break;

                    case 'CUSTOM':
                        if (event.name === 'render_component' && event.value) {
                            this.updateMessages(sessionId, (prev) =>
                                prev.map((msg) => {
                                    if (msg.id === aiMsgId) {
                                        const parts = msg.contentParts || [];
                                        return {
                                            ...msg,
                                            contentParts: [...parts, {
                                                type: 'component' as const,
                                                component: {
                                                    name: event.value.component,
                                                    props: event.value.props
                                                }
                                            }]
                                        };
                                    }
                                    return msg;
                                })
                            );
                        }
                        break;

                    case 'RUN_FINISHED':
                        this.setMessageMarkdown(sessionId, aiMsgId, totalMessageAccumulated);
                        this.updateMessages(sessionId, (prev) =>
                            prev.map((msg) => {
                                if (msg.id === aiMsgId) {
                                    return {
                                        ...msg,
                                        status: 'ended' as const,
                                    };
                                }
                                return msg;
                            })
                        );
                        this.setAIRunning(sessionId, false);
                        break;
                }
            }
        } catch (error) {
            console.error('API 事件流处理错误:', error);
            this.setAIRunning(sessionId, false);

            this.updateMessages(sessionId, (prev) => {
                const hasAiMsg = prev.some(msg => msg.id === aiMsgId);
                if (hasAiMsg) {
                    return prev.map((msg) =>
                        msg.id === aiMsgId
                            ? {
                                ...msg,
                                message: errorMessage,
                                status: 'ended' as const,
                            }
                            : msg
                    );
                } else {
                    return [
                        ...prev,
                        {
                            id: aiMsgId,
                            message: errorMessage,
                            status: 'ended' as const,
                            timestamp: Date.now(),
                        }
                    ];
                }
            });
        }
    }
}

// 创建全局单例
const conversationManager = new ConversationManager();

/**
 * Context 类型定义
 */
interface ConversationContextType {
    manager: ConversationManager;
    runningSessionIds: string[];
}

const ConversationContext = createContext<ConversationContextType | null>(null);

/**
 * Provider 组件
 */
export const ConversationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    // 使用 useSyncExternalStore 订阅全局状态变化
    // _sessions 用于触发组件重渲染，当全局状态变化时会重新获取 runningSessionIds
    const _sessions = useSyncExternalStore(
        (callback) => conversationManager.subscribe(callback),
        () => conversationManager.getSnapshot(),
        () => conversationManager.getSnapshot()
    );

    // 计算正在运行的会话 ID（依赖上面的订阅触发更新）
    const runningSessionIds = conversationManager.getRunningSessionIds();

    return (
        <ConversationContext.Provider value={{ manager: conversationManager, runningSessionIds }}>
            {children}
        </ConversationContext.Provider>
    );
};

/**
 * Hook: 获取全局会话管理器
 */
export const useConversationManager = () => {
    const context = useContext(ConversationContext);
    if (!context) {
        throw new Error('useConversationManager must be used within ConversationProvider');
    }
    return context;
};

/**
 * Hook: 获取指定会话的状态
 */
export const useSessionState = (sessionId: string) => {
    const { manager } = useConversationManager();

    // 订阅状态变化
    const state = useSyncExternalStore(
        (callback) => manager.subscribe(callback),
        () => manager.getSessionState(sessionId),
        () => manager.getSessionState(sessionId)
    );

    return state;
};

/**
 * Hook: 获取所有正在运行 AI 的会话 ID 列表
 */
export const useRunningSessionIds = () => {
    const { manager } = useConversationManager();

    const runningIds = useSyncExternalStore(
        (callback) => manager.subscribe(callback),
        () => manager.getRunningSessionIds(),
        () => manager.getRunningSessionIds()
    );

    return runningIds;
};

export { conversationManager };
