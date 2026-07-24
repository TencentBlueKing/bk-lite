import React from 'react';
import { Avatar, Skeleton } from 'antd-mobile';
import { MenuOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import MobileSafeHeader from '@/components/mobile-safe-header';
import { ChatInfo } from '@/types/conversation';
import { useTranslation } from '@/utils/i18n';
import { buildConversationHref } from '@/utils/conversationRoute';

interface ConversationHeaderProps {
    chatInfo: ChatInfo | null;
    onMenuClick?: () => void;
    sidebarOpen?: boolean;
    loading?: boolean;
    nodeId?: string;
}

export const ConversationHeader: React.FC<ConversationHeaderProps> = ({ chatInfo, onMenuClick, sidebarOpen = false, loading = false, nodeId }) => {
    const router = useRouter();
    const { t } = useTranslation();

    // 处理新建对话
    const handleNewConversation = () => {
        if (loading || !chatInfo) return;

        // 跳转到新对话
        router.push(buildConversationHref({ botId: chatInfo.id, nodeId }));
    };

    return (
        <MobileSafeHeader contentClassName="relative flex items-center justify-center px-14">
            <button
                type="button"
                onClick={() => onMenuClick?.()}
                className="absolute left-2 flex min-h-11 min-w-11 items-center justify-center rounded-lg text-[var(--color-text-1)] active:bg-[var(--color-fill-2)]"
                aria-label={t('chat.openConversationHistory')}
                aria-controls="conversation-history-drawer"
                aria-expanded={sidebarOpen}
            >
                <MenuOutlined className="text-xl" />
            </button>

            {loading ? (
                <div className="flex items-center">
                    <Skeleton.Title animated style={{ width: '36px', height: '36px', borderRadius: '50%', margin: '0 8px 0 0' }} className="mr-2" />
                    <Skeleton.Title animated style={{ width: '100px', height: '20px', margin: '0' }} />
                </div>
            ) : chatInfo ? (
                <div className="flex min-w-0 items-center">
                    <Avatar
                        src={chatInfo.avatar}
                        style={{ '--size': '36px', '--border-radius': '36px' }}
                        className="mr-2 flex-shrink-0"
                    />
                    <div className="truncate text-base font-medium text-[var(--color-text-1)]">
                        {chatInfo.name}
                    </div>
                </div>
            ) : null}

            <button
                type="button"
                onClick={handleNewConversation}
                className="absolute right-2 flex min-h-11 min-w-11 items-center justify-center rounded-lg active:bg-[var(--color-fill-2)] disabled:cursor-not-allowed"
                disabled={loading}
                aria-label={t('chat.newConversation')}
            >
                <span className={`iconfont icon-xinjianduihua text-2xl ${loading ? 'text-[var(--color-text-4)]' : 'text-[var(--color-text-1)]'}`}></span>
            </button>
        </MobileSafeHeader>
    );
};
