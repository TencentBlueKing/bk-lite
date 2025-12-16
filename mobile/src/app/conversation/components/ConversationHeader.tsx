import React from 'react';
import { Avatar } from 'antd-mobile';
import { LeftOutline, MoreOutline } from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import { ChatInfo } from '@/types/conversation';

interface ConversationHeaderProps {
    chatInfo: ChatInfo;
}

export const ConversationHeader: React.FC<ConversationHeaderProps> = ({ chatInfo }) => {
    const router = useRouter();

    return (
        <div className="flex items-center justify-center px-2 py-3 bg-[var(--color-bg)] border-b border-[var(--color-border)]">
            <button
                onClick={() => router.push('/conversations')}
                className="absolute left-4"
            >
                <LeftOutline fontSize={24} className="text-[var(--color-text-1)]" />
            </button>
            <div
                className="flex items-center cursor-pointer"
                onClick={() => router.push(`/workbench/detail?id=${chatInfo.id}`)}
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
            <button
                onClick={() => router.push(`/workbench/detail?id=${chatInfo.id}`)}
                className="absolute right-4"
            >
                <MoreOutline className="text-[var(--color-text-1)] text-3xl" />
            </button>
        </div>
    );
};
