import React from 'react';
import { Bubble, Actions } from '@ant-design/x';
import { type GetProp } from 'antd';
import { Message } from '@/types/conversation';
import { formatMessageTime, shouldShowTime } from '../utils/timeUtils';
import { actionItems } from '../utils/constants';
import { ToolCallItem } from './custom-components/ToolCallItem';
import { ApplicationForm, InformationCard, SelectionButtons } from './index';
import { useTranslation } from '@/utils/i18n';
interface MessageListProps {
    messages: Message[];
    router: any;
    thinkingExpanded: Record<string, boolean>;
    setThinkingExpanded: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
    thinkingTypingText: Record<string, string>;
    renderMarkdown: (text: string) => React.ReactNode;
    onActionClick: (key: string, messageId?: string) => void;
    onRecommendationClick: (text: string) => void;
    onFormSubmit?: (message: string) => void; // 用于表单提交发送消息
}

const getRoles: GetProp<typeof Bubble.List, 'roles'> = ({
    ai: {
        placement: 'start',
        shape: 'corner',
        style: {
            margin: '0 10px',
            maxWidth: '100%',
        },
    },
    local: {
        placement: 'end',
        variant: 'filled',
        shape: 'corner',
        style: {
            margin: '0 10px',
            maxWidth: '100%',
        },
        styles: {
            content: {
                backgroundColor: '#1677ff',
                color: '#ffffff',
            },
        },
    },
});

export const MessageList: React.FC<MessageListProps> = ({
    messages,
    thinkingExpanded,
    setThinkingExpanded,
    thinkingTypingText,
    renderMarkdown,
    onActionClick,
    onRecommendationClick,
    onFormSubmit,
}) => {
    const { t } = useTranslation();

    return (
        <>
            {messages.map((msg, index) => {
                const isAIMessage = msg.status !== 'local' && (msg.status === 'ended' || msg.status === 'history');
                const isLastAIMessage = isAIMessage && index === messages.length - 1;
                const isThinkingMessage = msg.status === 'thinking';
                const isHistoryMessage = msg.status === 'history';
                // 思考过程应该在所有非用户消息中显示（只要有 thinking 字段）
                const shouldShowThinking = msg.status !== 'local' && msg.thinking;

                let previousTimestamp: number | undefined;
                if (index > 0) {
                    previousTimestamp = messages[index - 1]?.timestamp;
                }

                const showTime = msg.timestamp && shouldShowTime(msg.timestamp, previousTimestamp);

                // 欢迎消息特殊处理
                if (msg.isWelcome && typeof msg.message === 'object' && msg.message !== null && 'text' in msg.message && 'suggestions' in msg.message) {
                    const welcomeMsg = msg.message as { text: string; suggestions: string[] };
                    return (
                        <React.Fragment key={msg.id}>
                            {showTime && (
                                <div className="flex justify-center">
                                    <div className="text-xs text-[var(--color-text-4)] px-3 py-1">
                                        {formatMessageTime(msg.timestamp, t)}
                                    </div>
                                </div>
                            )}
                            <Bubble.List
                                roles={getRoles}
                                style={{ width: '100%' }}
                                className="w-full"
                                items={[{
                                    key: `${msg.id}-text`,
                                    role: 'ai',
                                    content: welcomeMsg.text,
                                }]}
                            />
                            {welcomeMsg.suggestions.length > 0 && (
                                <div className="flex flex-col items-start gap-2 ml-3 mt-2">
                                    {welcomeMsg.suggestions.map((item: string, idx: number) => (
                                        <div
                                            key={idx}
                                            onClick={() => onRecommendationClick(item)}
                                            className="recommendation-item py-2.5 px-4 rounded-xl cursor-pointer text-sm text-[var(--color-text-2)] border border-[var(--color-border)] shadow-sm inline-block"
                                        >
                                            {item}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </React.Fragment>
                    );
                }

                const showActions = isAIMessage && !msg.isWelcome;
                const normalizedContent = Array.isArray(msg.message)
                    ? (
                        <>
                            {msg.message.map((child: any, i: number) => (
                                <React.Fragment key={i}>{child}</React.Fragment>
                            ))}
                        </>
                    )
                    : msg.message;

                // 如果有 contentParts,使用新的渲染逻辑
                let contentWithCustomComponent = normalizedContent;

                if (msg.contentParts && msg.contentParts.length > 0) {
                    // 使用 contentParts 渲染(支持文本、组件和工具调用交替)
                    contentWithCustomComponent = (
                        <>
                            {msg.contentParts.map((part, idx) => {
                                if (part.type === 'text') {
                                    // 检查文本内容是否为空，避免渲染空白
                                    if (!part.content) {
                                        console.log('MessageList: Skipping empty text part at index', idx);
                                        return null;
                                    }
                                    return <React.Fragment key={`text-${idx}`}>{part.content}</React.Fragment>;
                                } else if (part.type === 'tool_call' && part.toolCall) {
                                    // 渲染工具调用
                                    return (
                                        <div key={`tool-${idx}`} className="my-3">
                                            <ToolCallItem toolCall={part.toolCall} />
                                        </div>
                                    );
                                } else if (part.type === 'component' && part.component) {
                                    const ComponentName = part.component.name;
                                    if (ComponentName === 'ApplicationForm') {
                                        return (
                                            <div key={`comp-${idx}`} className="my-3">
                                                <ApplicationForm
                                                    {...part.component.props}
                                                    onFormSubmit={onFormSubmit}
                                                />
                                            </div>
                                        );
                                    } else if (ComponentName === 'InformationCard') {
                                        return (
                                            <div key={`comp-${idx}`} className="my-3">
                                                <InformationCard
                                                    {...part.component.props}
                                                    onButtonClick={onFormSubmit}
                                                />
                                            </div>
                                        );
                                    } else if (ComponentName === 'SelectionButtons') {
                                        return (
                                            <div key={`comp-${idx}`} className="my-3">
                                                <SelectionButtons
                                                    {...part.component.props}
                                                    onButtonClick={onFormSubmit}
                                                />
                                            </div>
                                        );
                                    }
                                }
                                return null;
                            })}
                        </>
                    );
                }
                const currentActionItems = (isLastAIMessage && !isHistoryMessage)
                    ? actionItems
                    : [actionItems[0]];

                // 只有在 thinking 状态时才隐藏消息气泡
                // loading 状态需要显示加载动画
                const shouldHideMessage = isThinkingMessage;
                const shouldShowLoading = msg.status === 'loading';

                return (
                    <React.Fragment key={msg.id}>
                        {showTime && (
                            <div className="flex justify-center">
                                <div className="text-xs text-[var(--color-text-4)] px-3 py-1">
                                    {formatMessageTime(msg.timestamp, t)}
                                </div>
                            </div>
                        )}

                        {shouldShowThinking && (
                            <div className="mx-4 mt-3">
                                <div
                                    onClick={() => {
                                        setThinkingExpanded(prev => ({
                                            ...prev,
                                            [msg.id]: !prev[msg.id]
                                        }));
                                    }}
                                    className="thinking-process-header flex items-center gap-2 cursor-pointer py-2"
                                >
                                    <span
                                        className="thinking-arrow"
                                        style={{
                                            display: 'inline-block',
                                            transform: thinkingExpanded[msg.id] ? 'rotate(0deg)' : 'rotate(-90deg)'
                                        }}
                                    >
                                        ▼
                                    </span>
                                    <span className="text-sm text-[var(--color-text-1)] font-medium">
                                        思考过程
                                    </span>
                                </div>
                                {thinkingExpanded[msg.id] && (
                                    <div className="text-sm text-[var(--color-text-2)]">
                                        {renderMarkdown(thinkingTypingText[msg.id] || msg.thinking || '')}
                                    </div>
                                )}
                            </div>
                        )}

                        {!shouldHideMessage && (
                            <Bubble.List
                                roles={getRoles}
                                style={{ width: '100%' }}
                                className="w-full"
                                items={[{
                                    key: msg.id,
                                    loading: shouldShowLoading,
                                    role: msg.status === 'local' ? 'local' : 'ai',
                                    content: contentWithCustomComponent,
                                    // 如果是文件消息，覆盖样式：无背景、无边框
                                    ...(msg.isFileMessage && {
                                        styles: {
                                            content: {
                                                backgroundColor: 'transparent',
                                                border: 'none',
                                                boxShadow: 'none',
                                                padding: 0,
                                            }
                                        }
                                    }),
                                    ...(showActions && {
                                        footer: (
                                            <Actions
                                                items={currentActionItems}
                                                onClick={({ keyPath }) =>
                                                    onActionClick(keyPath[0], msg.id)
                                                }
                                            />
                                        ),
                                    }),
                                }]}
                            />
                        )}
                    </React.Fragment>
                );
            })}
        </>
    );
};
