import React from 'react';
import { Bubble, Actions } from '@ant-design/x';
import { type GetProp } from 'antd';
import { Message } from '../hooks/useMessages';
import { formatMessageTime, shouldShowTime } from '../utils/timeUtils';
import { actionItems } from '../utils/constants';
import { ChatInfo } from '@/types/conversation';
import { ToolCallsDisplay } from './ToolCallsDisplay';
import { ApplicationForm } from './ApplicationForm';
import { InformationCard } from './InformationCard';

interface MessageListProps {
    messages: Message[];
    chatInfo: ChatInfo;
    router: any;
    thinkingExpanded: Record<string, boolean>;
    setThinkingExpanded: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
    thinkingTypingText: Record<string, string>;
    renderMarkdown: (text: string) => React.ReactNode;
    onActionClick: (key: string, message: string | React.ReactNode, messageId?: string) => void;
    onRecommendationClick: (text: string) => void;
    onRegenerateRecommendations: () => void;
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
            maxWidth: '90%',
            marginRight: '10px',
            marginLeft: 'auto',
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
    onRegenerateRecommendations,
    onFormSubmit,
}) => {
    return (
        <>
            {messages.map((msg, index) => {
                const isAIMessage = msg.status !== 'local' && msg.status !== 'loading' && msg.status !== 'thinking';
                const isLastAIMessage = isAIMessage && index === messages.length - 1;
                const isThinkingMessage = msg.status === 'thinking';
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
                                        {formatMessageTime(msg.timestamp)}
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
                            <div className="ml-3 mt-2 flex justify-start">
                                <div
                                    onClick={onRegenerateRecommendations}
                                    className="regenerate-button flex items-center justify-center"
                                >
                                    <span className='iconfont icon-shuaxin text-sm font-bold' />
                                </div>
                            </div>
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

                // 如果有自定义组件，将其添加到内容中
                let contentWithCustomComponent = normalizedContent;

                if (msg.customComponent) {
                    if (msg.customComponent.component === 'ApplicationForm') {
                        contentWithCustomComponent = (
                            <>
                                {normalizedContent}
                                <div className="mt-3">
                                    <ApplicationForm
                                        {...msg.customComponent.props}
                                        onFormSubmit={onFormSubmit}
                                    />
                                </div>
                            </>
                        );
                    } else if (msg.customComponent.component === 'InformationCard') {
                        contentWithCustomComponent = (
                            <>
                                {normalizedContent}
                                <div className="mt-3">
                                    <InformationCard
                                        {...msg.customComponent.props}
                                        onButtonClick={onFormSubmit}
                                    />
                                </div>
                            </>
                        );
                    }
                }



                const currentActionItems = isLastAIMessage
                    ? actionItems
                    : [actionItems[0]];

                // AG-UI 协议：思考过程完成后才显示消息
                const shouldHideMessage = isThinkingMessage || msg.status === 'loading';
                const shouldShowLoading = msg.status === 'loading';
                const shouldUseTyping = false;

                return (
                    <React.Fragment key={msg.id}>
                        {showTime && (
                            <div className="flex justify-center">
                                <div className="text-xs text-[var(--color-text-4)] px-3 py-1">
                                    {formatMessageTime(msg.timestamp)}
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

                        {/* 工具调用展示 - 位于思考过程和 AI 回复之间 */}
                        {msg.toolCalls && msg.toolCalls.length > 0 && (
                            <ToolCallsDisplay
                                toolCalls={msg.toolCalls}
                                isRunFinished={msg.isRunFinished}
                            />
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
                                    typing: shouldUseTyping ? { step: 3, interval: 30 } : false,
                                    ...(showActions && {
                                        footer: (
                                            <Actions
                                                items={currentActionItems}
                                                onClick={({ keyPath }) =>
                                                    onActionClick(keyPath[0], msg.message as React.ReactNode, msg.id)
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
