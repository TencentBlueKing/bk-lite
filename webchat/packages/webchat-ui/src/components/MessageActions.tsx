import React from 'react';

interface MessageActionsProps {
  messageId: string;
  messageContent: string;
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
      className={`flex items-center gap-0.5 px-2 text-xs h-6 ${
        isBot ? 'ml-10' : 'mr-10 justify-end'
      } ${showActions ? 'opacity-100' : 'opacity-0'} transition-opacity`}
    >
      {isLastBotMessage && (
        <button
          onClick={() => onRegenerate?.(messageId)}
          className="p-1 hover:bg-gray-100 rounded transition-colors"
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
            className="text-gray-500"
          >
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
          </svg>
        </button>
      )}
      <button
        onClick={() => {
          navigator.clipboard.writeText(messageContent);
          onCopy?.(messageContent);
        }}
        className="p-1 hover:bg-gray-100 rounded transition-colors"
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
          className="text-gray-500"
        >
          <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
          <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
        </svg>
      </button>
      <button
        onClick={() => onDelete?.(messageId)}
        className="p-1 hover:bg-gray-100 rounded transition-colors"
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
          className="text-gray-500"
        >
          <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
        </svg>
      </button>
    </div>
  );
};
