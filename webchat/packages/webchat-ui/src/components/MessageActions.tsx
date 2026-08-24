import React from 'react';
import { MessageContent } from '@webchat/core';

interface MessageActionsProps {
  messageId: string;
  messageContent: string | MessageContent[];
  isBot: boolean;
  isLastBotMessage?: boolean;
  showActions: boolean;
  onRegenerate?: (messageId: string) => void;
  onCopy?: (content: string) => void;
  onDelete?: (messageId: string) => void;
}

export const MessageActions: React.FC<MessageActionsProps> = ({
  messageId,
  messageContent,
  isBot,
  isLastBotMessage,
  showActions,
  onRegenerate,
  onCopy,
  onDelete,
}) => {
  return (
    <div
      className={`flex h-6 items-center gap-0.5 px-2 text-xs ${
        isBot ? 'ml-10' : 'mr-10 justify-end'
      } ${showActions ? 'opacity-100' : 'opacity-0'}`}
    >
      {isLastBotMessage && (
        <button
          onClick={() => onRegenerate?.(messageId)}
          className="rounded p-1 text-[var(--color-text-3,#86909c)] hover:bg-[var(--color-fill-2,#f4f6fa)] hover:text-[var(--color-text-1,#1d2129)]"
          title="重新生成"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
          </svg>
        </button>
      )}
      <button
        onClick={() => {
          const text = Array.isArray(messageContent)
            ? messageContent
                .filter((item) => item.type === 'text' && item.text)
                .map((item) => item.text)
                .join('\n')
            : messageContent;
          navigator.clipboard.writeText(text);
          onCopy?.(text);
        }}
        className="rounded p-1 text-[var(--color-text-3,#86909c)] hover:bg-[var(--color-fill-2,#f4f6fa)] hover:text-[var(--color-text-1,#1d2129)]"
        title="复制"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
          <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
        </svg>
      </button>
      <button
        onClick={() => onDelete?.(messageId)}
        className="rounded p-1 text-[var(--color-text-3,#86909c)] hover:bg-[var(--color-fill-2,#f4f6fa)] hover:text-[var(--color-text-1,#1d2129)]"
        title="删除"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
        </svg>
      </button>
    </div>
  );
};
