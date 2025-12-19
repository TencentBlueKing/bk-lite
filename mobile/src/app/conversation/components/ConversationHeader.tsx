import React from 'react';
import { Avatar, Skeleton } from 'antd-mobile';
import { MenuOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { ChatInfo } from '@/types/conversation';

interface ConversationHeaderProps {
    chatInfo: ChatInfo | null;
    onMenuClick?: () => void;
    loading?: boolean;
}

export const ConversationHeader: React.FC<ConversationHeaderProps> = ({ chatInfo, onMenuClick, loading = false }) => {
    const router = useRouter();

    // 处理新建对话
    const handleNewConversation = () => {
        if (loading || !chatInfo) return;

        // 跳转到新对话（不带session_id，添加时间戳强制刷新）
        const timestamp = Date.now();
        router.push(`/conversation?bot_id=${chatInfo.id}&t=${timestamp}`);
    };

    return (
        <div className="flex items-center justify-center px-2 py-3 bg-[var(--color-bg)] border-b border-[var(--color-border)]">
            <button
                onClick={() => onMenuClick?.()}
                className="absolute left-4 text-[var(--color-text-1)]"
            >
                <MenuOutlined className="text-xl" />
            </button>

            {loading ? (
                <div className="flex items-center">
                    <Skeleton.Title animated style={{ width: '36px', height: '36px', borderRadius: '50%', margin: '0 8px 0 0' }} className="mr-2" />
                    <Skeleton.Title animated style={{ width: '100px', height: '20px', margin: '0' }} />
                </div>
            ) : chatInfo ? (
                <div
                    className="flex items-center cursor-pointer"
                    onClick={() => router.push(`/workbench/detail?bot_id=${chatInfo.id}`)}
                >
                    <Avatar
                        src={chatInfo.avatar}
                        style={{ '--size': '36px', '--border-radius': '36px' }}
                        className="mr-2 flex-shrink-0"
                    />
                    <div className="text-base font-medium text-[var(--color-text-1)]">
                        {chatInfo.name}
                    </div>
                </div>
            ) : null}

            <button
                onClick={handleNewConversation}
                className="absolute right-4"
                disabled={loading}
            >
                <span className={`iconfont icon-xinjianduihua text-2xl ${loading ? 'text-[var(--color-text-4)]' : 'text-[var(--color-text-1)]'}`}></span>
            </button>
        </div>
    );
};
