import { useState, useRef, useEffect, useCallback, useSyncExternalStore } from 'react';
import type { Message, MessageContentItem } from '@/types/conversation';
import { conversationManager } from '@/context/conversation';

interface UseMessagesReturn {
    messages: Message[];
    setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
    handleSendMessage: (content: string, renderMarkdown: (text: string) => React.ReactNode) => Promise<void>;
    triggerAIResponse: (content: string | MessageContentItem[], renderMarkdown: (text: string) => React.ReactNode) => Promise<void>;
    thinkingExpanded: Record<string, boolean>;
    setThinkingExpanded: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
    thinkingTypingText: Record<string, string>;
    setThinkingTypingText: React.Dispatch<React.SetStateAction<Record<string, string>>>;
    messageMarkdownRef: React.MutableRefObject<Map<string, string>>;
    scrollToBottom: () => void;
    isAIRunning: boolean;
}

interface UseMessagesOptions {
    errorMessage?: string; // 国际化的错误消息
    bot?: number; // Bot ID
    nodeId?: string; // Node ID
    sessionId?: string; // Session ID
}

/**
 * 消息管理 Hook - 与全局 ConversationManager 集成
 * 支持会话切换时保持 AI 响应状态
 */
export const useMessages = (
    scrollContainerRef: React.RefObject<HTMLDivElement | null>,
    options?: UseMessagesOptions
): UseMessagesReturn => {
    const { errorMessage: customErrorMessage, bot, nodeId, sessionId } = options || {};

    // 订阅全局状态
    const globalState = useSyncExternalStore(
        (callback) => conversationManager.subscribe(callback),
        () => sessionId ? conversationManager.getSessionState(sessionId) : undefined,
        () => sessionId ? conversationManager.getSessionState(sessionId) : undefined
    );

    // 本地状态（用于没有 sessionId 或全局状态不存在时的回退）
    const [localMessages, setLocalMessages] = useState<Message[]>([]);
    const [localThinkingExpanded, setLocalThinkingExpanded] = useState<Record<string, boolean>>({});
    const [localThinkingTypingText, setLocalThinkingTypingText] = useState<Record<string, string>>({});

    // Markdown 原文存储
    const messageMarkdownRef = useRef<Map<string, string>>(new Map());

    // 存储 renderMarkdown 函数
    const renderMarkdownRef = useRef<((text: string) => React.ReactNode) | null>(null);

    // 判断是否使用全局状态
    const useGlobalState = Boolean(sessionId);

    // 同步全局状态到本地 ref（用于 messageMarkdownRef）
    // 当 sessionId 变化时，先清空旧数据再同步新数据
    useEffect(() => {
        if (useGlobalState && sessionId) {
            // 先清空旧数据
            messageMarkdownRef.current.clear();
            // 再从全局状态同步
            if (globalState) {
                globalState.messageMarkdown.forEach((value, key) => {
                    messageMarkdownRef.current.set(key, value);
                });
            }
        }
    }, [useGlobalState, sessionId, globalState]);

    // 初始化会话状态
    useEffect(() => {
        if (sessionId) {
            conversationManager.initSession(sessionId);
        }
    }, [sessionId]);

    // 获取当前状态（优先使用全局状态）
    const messages = useGlobalState && globalState ? globalState.messages : localMessages;
    const thinkingExpanded = useGlobalState && globalState ? globalState.thinkingExpanded : localThinkingExpanded;
    const thinkingTypingText = useGlobalState && globalState ? globalState.thinkingTypingText : localThinkingTypingText;
    const isAIRunning = useGlobalState && globalState ? globalState.isAIRunning : false;

    // 滚动到底部
    const scrollToBottom = useCallback(() => {
        if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
        }
    }, [scrollContainerRef]);

    // 设置消息的包装函数
    const setMessages: React.Dispatch<React.SetStateAction<Message[]>> = useCallback((action) => {
        if (useGlobalState && sessionId) {
            if (typeof action === 'function') {
                conversationManager.updateMessages(sessionId, action);
            } else {
                conversationManager.setMessages(sessionId, action);
            }
        } else {
            setLocalMessages(action);
        }
    }, [useGlobalState, sessionId]);

    // 设置思考过程展开状态
    const setThinkingExpanded: React.Dispatch<React.SetStateAction<Record<string, boolean>>> = useCallback((action) => {
        if (useGlobalState && sessionId) {
            if (typeof action === 'function') {
                const currentValue = conversationManager.getSessionState(sessionId)?.thinkingExpanded || {};
                const newValue = action(currentValue);
                conversationManager.setThinkingExpanded(sessionId, newValue);
            } else {
                conversationManager.setThinkingExpanded(sessionId, action);
            }
        } else {
            setLocalThinkingExpanded(action);
        }
    }, [useGlobalState, sessionId]);

    // 设置思考过程文本
    const setThinkingTypingText: React.Dispatch<React.SetStateAction<Record<string, string>>> = useCallback((action) => {
        if (useGlobalState && sessionId) {
            if (typeof action === 'function') {
                const currentValue = conversationManager.getSessionState(sessionId)?.thinkingTypingText || {};
                const newValue = action(currentValue);
                conversationManager.setThinkingTypingText(sessionId, newValue);
            } else {
                conversationManager.setThinkingTypingText(sessionId, action);
            }
        } else {
            setLocalThinkingTypingText(action);
        }
    }, [useGlobalState, sessionId]);

    // 发送消息 - 使用全局管理器
    const handleSendMessage = useCallback(async (
        content: string,
        renderMarkdown: (text: string) => React.ReactNode
    ) => {
        renderMarkdownRef.current = renderMarkdown;

        if (document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
        }

        if (!bot || !nodeId) {
            console.error('Missing bot or nodeId configuration');
            return;
        }

        if (!sessionId) {
            console.error('Missing sessionId');
            return;
        }

        // 使用全局管理器发送消息
        await conversationManager.startAIResponse(
            sessionId,
            bot,
            nodeId,
            content,
            renderMarkdown,
            customErrorMessage || '响应异常，请稍后再试',
            true
        );
    }, [bot, nodeId, sessionId, customErrorMessage]);

    // 只触发 AI 响应，不添加用户消息（用于文件消息场景）
    const triggerAIResponse = useCallback(async (
        content: string | MessageContentItem[],
        renderMarkdown: (text: string) => React.ReactNode
    ) => {
        renderMarkdownRef.current = renderMarkdown;

        if (!bot || !nodeId) {
            console.error('Missing bot or nodeId configuration');
            return;
        }

        if (!sessionId) {
            console.error('Missing sessionId');
            return;
        }

        // 使用全局管理器触发 AI 响应
        await conversationManager.startAIResponse(
            sessionId,
            bot,
            nodeId,
            content,
            renderMarkdown,
            customErrorMessage || '响应异常，请稍后再试',
            false
        );
    }, [bot, nodeId, sessionId, customErrorMessage]);

    // 监听消息变化，滚动到底部
    useEffect(() => {
        scrollToBottom();
    }, [messages, scrollToBottom]);

    return {
        messages,
        setMessages,
        handleSendMessage,
        triggerAIResponse,
        thinkingExpanded,
        setThinkingExpanded,
        thinkingTypingText,
        setThinkingTypingText,
        messageMarkdownRef,
        scrollToBottom,
        isAIRunning,
    };
};
