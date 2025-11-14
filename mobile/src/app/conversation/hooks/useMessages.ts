import { useState, useRef, useEffect } from 'react';
import { simulateAGUIStream } from '../utils/aiUtils';

export interface ToolCall {
    id: string;
    name: string;
    args: string;
    result?: any;
    status: 'executing' | 'completed';
}

export interface Message {
    id: string;
    message: string | React.ReactNode | null | { text: string; suggestions: string[] };
    status: 'local' | 'ai' | 'thinking' | 'loading' | 'success';
    timestamp: number;
    thinking?: string;
    userInput?: string;
    isWelcome?: boolean;
    toolCalls?: ToolCall[];
    isRunFinished?: boolean; // AI 是否已运行完成
    customComponent?: {
        component: string;
        props: any;
    }; // 自定义组件配置
}

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

export const useMessages = (
    scrollContainerRef: React.RefObject<HTMLDivElement>
): UseMessagesReturn => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [thinkingExpanded, setThinkingExpanded] = useState<Record<string, boolean>>({});
    const [thinkingTypingText, setThinkingTypingText] = useState<Record<string, string>>({});
    const [isAIRunning, setIsAIRunning] = useState<boolean>(false);

    const messageMarkdownRef = useRef<Map<string, string>>(new Map());
    const lastSendTimeRef = useRef<number>(0);
    const messageTimestampsRef = useRef<Map<string, number>>(new Map());
    const prevMessagesRef = useRef<Message[]>([]);

    // 滚动到底部
    const scrollToBottom = () => {
        if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
        }
    };

    // 存储 renderMarkdown 函数
    const renderMarkdownRef = useRef<((text: string) => React.ReactNode) | null>(null);

    /**
     * 处理 AG-UI 事件流
     */
    const handleAGUIEventStream = async (
        userMessage: string,
        aiMsgId: string,
        renderMarkdown: (text: string) => React.ReactNode
    ) => {
        // 存储思考过程和消息内容的累积文本
        let thinkingAccumulated = '';
        let messageAccumulated = '';
        let scrollCounter = 0;
        // 存储工具调用的参数累积
        const toolArgsAccumulated: Record<string, string> = {};

        try {
            // 获取事件流生成器
            const eventStream = simulateAGUIStream(userMessage, aiMsgId);

            // 处理每个事件
            for await (const event of eventStream) {
                console.log('Received AG-UI event:', event);

                switch (event.type) {
                    case 'RUN_STARTED':
                        // AI 运行开始，创建 AI 消息并禁用输入
                        setIsAIRunning(true);
                        setMessages((prev) => [
                            ...prev,
                            {
                                id: aiMsgId,
                                message: null,
                                status: 'thinking',
                                timestamp: event.timestamp,
                                thinking: '',
                                userInput: userMessage,
                                toolCalls: [],
                            }
                        ]);
                        break;

                    case 'THINKING_START':
                        // 思考过程开始，展开思考过程
                        setThinkingExpanded(prev => ({ ...prev, [aiMsgId]: true }));
                        break;

                    case 'THINKING_CONTENT':
                        // 累积思考过程文本
                        thinkingAccumulated += event.delta;

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
                        // 思考过程结束
                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, status: 'loading' }
                                    : msg
                            )
                        );
                        scrollToBottom();
                        break;

                    case 'TOOL_CALL':
                        // 工具调用开始
                        setMessages((prev) =>
                            prev.map((msg) => {
                                if (msg.id === aiMsgId) {
                                    const newToolCall: ToolCall = {
                                        id: event.toolCallId,
                                        name: event.toolCallName,
                                        args: '',
                                        status: 'executing',
                                    };
                                    return {
                                        ...msg,
                                        toolCalls: [...(msg.toolCalls || []), newToolCall],
                                    };
                                }
                                return msg;
                            })
                        );
                        toolArgsAccumulated[event.toolCallId] = '';
                        // 使用 requestAnimationFrame 确保 DOM 更新后再滚动
                        requestAnimationFrame(() => {
                            requestAnimationFrame(() => scrollToBottom());
                        });
                        break;

                    case 'TOOL_CALL_ARGS':
                        // 累积工具调用参数（前端不显示，但需要记录）
                        toolArgsAccumulated[event.toolCallId] += event.delta;
                        setMessages((prev) =>
                            prev.map((msg) => {
                                if (msg.id === aiMsgId && msg.toolCalls) {
                                    return {
                                        ...msg,
                                        toolCalls: msg.toolCalls.map(tool =>
                                            tool.id === event.toolCallId
                                                ? { ...tool, args: toolArgsAccumulated[event.toolCallId] }
                                                : tool
                                        ),
                                    };
                                }
                                return msg;
                            })
                        );
                        break;

                    case 'TOOL_CALL_END':
                        // 工具参数接收完成，等待执行结果
                        // 前端不需要特殊处理，保持 executing 状态
                        break;

                    case 'TOOL_RESULT':
                        // 工具执行结果返回
                        setMessages((prev) =>
                            prev.map((msg) => {
                                if (msg.id === aiMsgId && msg.toolCalls) {
                                    return {
                                        ...msg,
                                        toolCalls: msg.toolCalls.map(tool =>
                                            tool.id === event.toolCallId
                                                ? { ...tool, result: event.result, status: 'completed' }
                                                : tool
                                        ),
                                    };
                                }
                                return msg;
                            })
                        );
                        // 使用 requestAnimationFrame 确保 DOM 更新后再滚动
                        requestAnimationFrame(() => {
                            requestAnimationFrame(() => scrollToBottom());
                        });
                        break;

                    case 'TEXT_MESSAGE_START':
                        // AI 回复开始，更新状态
                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? { ...msg, status: 'loading' }
                                    : msg
                            )
                        );
                        break;

                    case 'TEXT_MESSAGE_CONTENT':
                        // 累积消息文本
                        messageAccumulated += event.delta;

                        // 保存原始 Markdown 文本
                        messageMarkdownRef.current.set(aiMsgId, messageAccumulated);

                        // 实时渲染累积的 Markdown 文本
                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? {
                                        ...msg,
                                        message: renderMarkdown(messageAccumulated),
                                        status: 'success',
                                    }
                                    : msg
                            )
                        );

                        // 定期滚动到底部
                        scrollCounter++;
                        if (scrollCounter % 3 === 0) {
                            requestAnimationFrame(() => scrollToBottom());
                        }
                        break;

                    case 'TEXT_MESSAGE_END':
                        // 消息结束，最终渲染
                        messageMarkdownRef.current.set(aiMsgId, messageAccumulated);
                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === aiMsgId
                                    ? {
                                        ...msg,
                                        message: renderMarkdown(messageAccumulated),
                                        status: 'success',
                                    }
                                    : msg
                            )
                        );
                        scrollToBottom();
                        break;

                    case 'CUSTOM':
                        // 自定义事件，用于渲染特殊组件
                        if (event.name === 'render_component') {
                            setMessages((prev) =>
                                prev.map((msg) =>
                                    msg.id === aiMsgId
                                        ? {
                                            ...msg,
                                            customComponent: {
                                                component: event.value.component,
                                                props: event.value.props,
                                            },
                                        }
                                        : msg
                                )
                            );
                            // 滚动到底部显示自定义组件
                            requestAnimationFrame(() => {
                                requestAnimationFrame(() => scrollToBottom());
                            });
                        }
                        break;

                    case 'RUN_FINISHED':
                        // AI 运行结束，恢复输入，标记消息为已完成
                        setIsAIRunning(false);
                        setMessages((prev) =>
                            prev.map((msg) => {
                                if (msg.id === aiMsgId) {
                                    return {
                                        ...msg,
                                        isRunFinished: true,
                                    };
                                }
                                return msg;
                            })
                        );
                        break;
                }
            }
        } catch (error) {
            console.error('AG-UI 事件流处理错误:', error);
            // 错误处理：恢复输入状态
            setIsAIRunning(false);
            // 显示错误消息
            setMessages((prev) =>
                prev.map((msg) =>
                    msg.id === aiMsgId
                        ? {
                            ...msg,
                            message: '抱歉，处理消息时出现错误，请重试。',
                            status: 'success',
                        }
                        : msg
                )
            );
        }
    };

    // 发送消息
    const handleSendMessage = async (content: string, renderMarkdown: (text: string) => React.ReactNode) => {
        const userMessageTimestamp = Date.now();
        lastSendTimeRef.current = userMessageTimestamp;
        renderMarkdownRef.current = renderMarkdown;

        if (document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
        }

        // 添加用户消息（渲染 Markdown）
        const userMsgId = `user-${Date.now()}`;
        messageMarkdownRef.current.set(userMsgId, content);
        setMessages((prev) => [
            ...prev,
            {
                id: userMsgId,
                message: renderMarkdown(content), // 渲染 Markdown
                status: 'local',
                timestamp: userMessageTimestamp,
            }
        ]);

        // 创建 AI 消息 ID
        const aiMsgId = `ai-${Date.now()}`;

        // 使用 AG-UI 协议处理事件流
        await handleAGUIEventStream(content, aiMsgId, renderMarkdown);
    };

    // 只触发 AI 响应，不添加用户消息（用于文件消息场景）
    const triggerAIResponse = async (content: string, renderMarkdown: (text: string) => React.ReactNode) => {
        lastSendTimeRef.current = Date.now();
        renderMarkdownRef.current = renderMarkdown;

        // 创建 AI 消息 ID
        const aiMsgId = `ai-${Date.now()}`;

        // 使用 AG-UI 协议处理事件流
        await handleAGUIEventStream(content, aiMsgId, renderMarkdown);
    };

    // 监听消息变化，为新消息添加时间戳
    useEffect(() => {
        if (lastSendTimeRef.current > 0) {
            const messagesChanged = messages.length !== prevMessagesRef.current.length ||
                messages.some((msg, index) => {
                    const prevMsg = prevMessagesRef.current[index];
                    return !prevMsg || msg.id !== prevMsg.id || msg.status !== prevMsg.status || msg.timestamp !== prevMsg.timestamp;
                });

            if (!messagesChanged) {
                return;
            }

            const needsUpdate = messages.some((msg) => !msg.timestamp || (!msg.thinking && msg.status === 'success'));

            if (needsUpdate) {
                const updatedMessages = messages.map((msg) => {
                    if (msg.timestamp && msg.thinking) {
                        return msg;
                    }

                    let timestamp = msg.timestamp;
                    if (!timestamp && messageTimestampsRef.current.has(msg.id)) {
                        timestamp = messageTimestampsRef.current.get(msg.id)!;
                    }

                    if (!timestamp) {
                        const isUserMessage = msg.status === 'local';
                        timestamp = isUserMessage
                            ? lastSendTimeRef.current
                            : lastSendTimeRef.current + 1500;

                        messageTimestampsRef.current.set(msg.id, timestamp);
                    }

                    return {
                        ...msg,
                        timestamp,
                    };
                });

                prevMessagesRef.current = updatedMessages;
                setMessages(updatedMessages);
            } else {
                prevMessagesRef.current = messages;
            }
        }
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
