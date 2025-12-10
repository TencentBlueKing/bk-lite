import { useState, useRef, useEffect } from 'react';
import { flushSync } from 'react-dom';
import { aiChatStream } from '@/api/bot';
import type { Message, ToolCall } from '@/types/conversation';

interface UseMessagesReturn {
    messages: Message[];
    setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
    handleSendMessage: (content: string, renderMarkdown: (text: string) => React.ReactNode) => Promise<void>;
    triggerAIResponse: (content: string, renderMarkdown: (text: string) => React.ReactNode) => Promise<void>;
    setRenderMarkdown: (renderMarkdown: (text: string) => React.ReactNode) => void;
    thinkingExpanded: Record<string, boolean>;
    setThinkingExpanded: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
    thinkingTypingText: Record<string, string>;
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

export const useMessages = (
    scrollContainerRef: React.RefObject<HTMLDivElement>,
    options?: UseMessagesOptions
): UseMessagesReturn => {
    const { errorMessage: customErrorMessage, bot, nodeId, sessionId } = options || {};
    const [messages, setMessages] = useState<Message[]>([]);
    const [thinkingExpanded, setThinkingExpanded] = useState<Record<string, boolean>>({});
    const [thinkingTypingText, setThinkingTypingText] = useState<Record<string, string>>({});
    const [isAIRunning, setIsAIRunning] = useState<boolean>(false);

    const messageMarkdownRef = useRef<Map<string, string>>(new Map());

    // 滚动到底部
    const scrollToBottom = () => {
        if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
        }
    };

    // 存储 renderMarkdown 函数
    const renderMarkdownRef = useRef<((text: string) => React.ReactNode) | null>(null);

    /**
     * 处理 AG-UI 事件流 - 使用真实 API
     */
    const handleAGUIEventStream = async (
        userMessage: string,
        aiMsgId: string,
        renderMarkdown: (text: string) => React.ReactNode
    ) => {
        // 存储思考过程和消息内容的累积文本
        let thinkingAccumulated = '';
        let currentTextSegmentIndex = 0;  // 当前文本段的索引
        let messageAccumulated = ''; // 当前文本段的累积
        let totalMessageAccumulated = ''; // 所有文本的总累积
        let scrollCounter = 0;
        // 存储工具调用的参数累积
        const toolArgsAccumulated: Record<string, string> = {};

        try {
            // 检查是否有有效的 bot 和 nodeId
            if (!bot || !nodeId) {
                throw new Error('Missing bot or nodeId configuration');
            }

            // 获取真实 API 事件流
            const eventStream = aiChatStream(bot, nodeId, userMessage, sessionId);

            // 处理每个事件
            for await (const event of eventStream) {
                console.log('Received API event:', event);

                switch (event.type) {
                    case 'RUN_STARTED':
                        // AI 运行开始确认，消息已经预先添加，这里只更新时间戳
                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, timestamp: event.timestamp || msg.timestamp }
                                    : msg
                            )
                        );
                        break;

                    case 'THINKING_START':
                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, status: 'thinking' }
                                    : msg
                            )
                        );
                        setThinkingExpanded(prev => ({ ...prev, [aiMsgId]: true }));
                        break;

                    case 'THINKING_CONTENT':
                        // 累积思考过程文本
                        thinkingAccumulated += event.delta || '';

                        // 实时更新思考过程显示
                        setThinkingTypingText(prev => ({
                            ...prev,
                            [aiMsgId]: thinkingAccumulated
                        }));

                        // 更新消息中的 thinking 字段
                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, thinking: thinkingAccumulated }
                                    : msg
                            )
                        );

                        // 定期滚动到底部
                        scrollCounter++;
                        if (scrollCounter % 3 === 0) {
                            requestAnimationFrame(() => scrollToBottom());
                        }
                        break;

                    case 'THINKING_END':
                        // 思考过程结束，切换到 loading 等待文本消息
                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, status: 'loading' }
                                    : msg
                            )
                        );
                        scrollToBottom();
                        break;

                    case 'TOOL_CALL_START':
                        // 工具调用开始
                        setMessages((prev) =>
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
                                        toolCalls: [...(msg.toolCalls || []), newToolCall],
                                        // 同时添加到 contentParts
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
                        requestAnimationFrame(() => {
                            requestAnimationFrame(() => scrollToBottom());
                        });
                        break;

                    case 'TOOL_CALL_ARGS':
                        // 累积工具调用参数
                        if (event.toolCallId) {
                            const toolCallId = event.toolCallId;
                            toolArgsAccumulated[toolCallId] = (toolArgsAccumulated[toolCallId] || '') + (event.delta || '');
                            setMessages((prev) =>
                                prev.map((msg) => {
                                    if (msg.id === aiMsgId && msg.toolCalls) {
                                        const updatedToolCalls = msg.toolCalls.map(tool =>
                                            tool.id === toolCallId
                                                ? { ...tool, args: toolArgsAccumulated[toolCallId] }
                                                : tool
                                        );
                                        // 同时更新 contentParts 中的工具调用
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
                                            toolCalls: updatedToolCalls,
                                            contentParts: updatedParts,
                                        };
                                    }
                                    return msg;
                                })
                            );
                        }
                        break;

                    case 'TOOL_CALL_END':
                        // 工具参数接收完成，等待执行结果
                        break;

                    case 'TOOL_CALL_RESULT':
                        // 工具执行结果返回
                        if (event.toolCallId) {
                            const toolCallId = event.toolCallId;
                            setMessages((prev) =>
                                prev.map((msg) => {
                                    if (msg.id === aiMsgId && msg.toolCalls) {
                                        const updatedToolCalls = msg.toolCalls.map(tool =>
                                            tool.id === toolCallId
                                                ? { ...tool, result: event.content, status: 'completed' as const }
                                                : tool
                                        );
                                        // 同时更新 contentParts 中的工具调用结果
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
                                            toolCalls: updatedToolCalls,
                                            contentParts: updatedParts,
                                        };
                                    }
                                    return msg;
                                })
                            );
                        }
                        requestAnimationFrame(() => {
                            requestAnimationFrame(() => scrollToBottom());
                        });
                        break;

                    case 'TEXT_MESSAGE_START':
                        // 重置累积器,准备下一段文本
                        messageAccumulated = '';
                        currentTextSegmentIndex++;
                        break;

                    case 'TEXT_MESSAGE_CONTENT':
                        // 累积消息文本 - 使用 delta 或 msg 字段
                        const textDelta = event.delta || event.msg || '';
                        messageAccumulated += textDelta;// 当前段落累积
                        totalMessageAccumulated += textDelta; // 累积总文本

                        // 实时渲染累积的 Markdown 文本
                        const renderedContent = renderMarkdown(messageAccumulated);

                        setMessages((prev) =>
                            prev.map((msg) => {
                                if (msg.id === aiMsgId) {
                                    const parts = msg.contentParts || [];
                                    const existingTextPartIndex = parts.findIndex(p =>
                                        p.type === 'text' && p.segmentIndex === currentTextSegmentIndex
                                    );

                                    if (existingTextPartIndex >= 0) {
                                        // 更新已有的文本段
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
                                        // 添加新的文本段
                                        return {
                                            ...msg,
                                            status: 'success',
                                            contentParts: [...parts, {
                                                type: 'text' as const,
                                                content: renderedContent,  // 总是渲染整个消息
                                                segmentIndex: currentTextSegmentIndex
                                            }]
                                        };
                                    }
                                }
                                return msg;
                            })
                        );

                        // 定期滚动到底部
                        scrollCounter++;
                        if (scrollCounter % 3 === 0) {
                            requestAnimationFrame(() => scrollToBottom());
                        }
                        break;

                    case 'TEXT_MESSAGE_END':
                        scrollToBottom();
                        break;

                    case 'CUSTOM':
                        // 自定义事件，用于渲染特殊组件
                        if (event.name === 'render_component' && event.value) {
                            setMessages((prev) =>
                                prev.map((msg) => {
                                    if (msg.id === aiMsgId) {
                                        const parts = msg.contentParts || [];
                                        return {
                                            ...msg,
                                            customComponent: {
                                                component: event.value.component,
                                                props: event.value.props,
                                            },
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
                            requestAnimationFrame(() => {
                                requestAnimationFrame(() => scrollToBottom());
                            });
                        }
                        break;

                    case 'RUN_FINISHED':
                        // AI 运行结束，恢复输入，标记消息为已完成
                        // 使用 flushSync 确保状态同步更新，避免被之前的异步更新覆盖
                        flushSync(() => {
                            setIsAIRunning(false);
                            // 保存原始 Markdown 文本（使用总累积）
                            messageMarkdownRef.current.set(aiMsgId, totalMessageAccumulated);
                            setMessages((prev) =>
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
                        });
                        break;
                }
            }
        } catch (error) {
            console.error('API 事件流处理错误:', error);
            setIsAIRunning(false);

            // 使用统一的国际化错误消息
            const errorMessage = customErrorMessage || '响应异常，请稍后再试';
            console.error('Error details:', error instanceof Error ? error.message : error);

            // 显示错误消息
            setMessages((prev) => {
                // 检查是否已经添加了 AI 消息
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
                    // 如果还没有添加 AI 消息，添加一个错误消息
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
    };

    // 发送消息
    const handleSendMessage = async (content: string, renderMarkdown: (text: string) => React.ReactNode) => {
        const userMessageTimestamp = Date.now();
        renderMarkdownRef.current = renderMarkdown;

        if (document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
        }

        // 添加用户消息（渲染 Markdown）
        const userMsgId = `user-${Date.now()}`;
        messageMarkdownRef.current.set(userMsgId, content);

        // 创建 AI 消息 ID
        const aiMsgId = `ai-${Date.now()}`;

        // 立即添加用户消息和 AI loading 消息，让用户看到即时反馈
        setIsAIRunning(true);
        setMessages((prev) => [
            ...prev,
            {
                id: userMsgId,
                message: renderMarkdown(content),
                status: 'local',
                timestamp: userMessageTimestamp,
            },
            {
                id: aiMsgId,
                message: null,
                status: 'loading',
                timestamp: Date.now(),
                thinking: '',
                userInput: content,
                toolCalls: [],
            }
        ]);

        // 使用 AG-UI 协议处理事件流
        await handleAGUIEventStream(content, aiMsgId, renderMarkdown);
    };

    // 只触发 AI 响应，不添加用户消息（用于文件消息场景）
    const triggerAIResponse = async (content: string, renderMarkdown: (text: string) => React.ReactNode) => {
        renderMarkdownRef.current = renderMarkdown;

        // 创建 AI 消息 ID
        const aiMsgId = `ai-${Date.now()}`;

        // 立即添加 AI loading 消息
        setIsAIRunning(true);
        setMessages((prev) => [
            ...prev,
            {
                id: aiMsgId,
                message: null,
                status: 'loading',
                timestamp: Date.now(),
                thinking: '',
                userInput: content,
                toolCalls: [],
            }
        ]);

        // 使用 AG-UI 协议处理事件流
        await handleAGUIEventStream(content, aiMsgId, renderMarkdown);
    };

    // 监听消息变化，滚动到底部
    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    // 暴露设置 renderMarkdown 的方法
    const setRenderMarkdown = (renderMarkdown: (text: string) => React.ReactNode) => {
        renderMarkdownRef.current = renderMarkdown;
    };

    return {
        messages,
        setMessages,
        handleSendMessage,
        triggerAIResponse,
        setRenderMarkdown,
        thinkingExpanded,
        setThinkingExpanded,
        thinkingTypingText,
        messageMarkdownRef,
        scrollToBottom,
        isAIRunning,
    };
};
