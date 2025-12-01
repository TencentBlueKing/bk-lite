import React, { useState } from 'react';
import { Bubble } from '@ant-design/x';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '@webchat/core';
import { MessageActions } from './MessageActions';
import { ConfirmDialog } from './ConfirmDialog';

interface MessageBubbleProps {
  message: Message;
  botAvatar: React.ReactElement;
  userAvatar: React.ReactElement;
  isLastBotMessage?: boolean;
  onRegenerate?: (messageId: string) => void;
  onCopy?: (content: string) => void;
  onDelete?: (messageId: string) => void;
}

export const MessageBubble: React.FC<MessageBubbleProps> = (
  ({ message, botAvatar, userAvatar, isLastBotMessage, onRegenerate, onCopy, onDelete }) => {
    const isBot = message.sender === 'bot';
    const [showActions, setShowActions] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    
    const content = isBot ? (
      <div className="prose prose-sm max-w-none prose-pre:bg-gray-100 prose-pre:text-gray-900 prose-hr:my-3 prose-h1:mt-3 prose-h1:mb-2 prose-h2:mt-3 prose-h2:mb-2 prose-h3:mt-2 prose-h3:mb-1 prose-h4:mt-2 prose-h4:mb-1 prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
      </div>
    ) : (
      message.content
    );

    const handleDelete = () => {
      setShowDeleteConfirm(false);
      onDelete?.(message.id);
    };

    return (
      <>
        <div
          onMouseEnter={() => setShowActions(true)}
          onMouseLeave={() => setShowActions(false)}
          className="flex flex-col"
        >
          <Bubble
            key={message.id}
            content={content}
            avatar={isBot ? botAvatar : userAvatar}
            placement={isBot ? 'start' : 'end'}
            styles={{
              content: {
                maxWidth: 'none',
                width: 'auto',
                maxHeight: 'none',
                overflow: 'visible'
              }
            }}
          />
          <MessageActions
            messageId={message.id}
            messageContent={message.content}
            isBot={isBot}
            isLastBotMessage={isLastBotMessage}
            showActions={showActions}
            onRegenerate={onRegenerate}
            onCopy={onCopy}
            onDelete={() => setShowDeleteConfirm(true)}
          />
        </div>
        <ConfirmDialog
          isOpen={showDeleteConfirm}
          title="是否删除该条消息？"
          message="删除后，聊天记录不可恢复，对话内的文件也将被彻底删除。"
          confirmText="删除"
          cancelText="取消"
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      </>
    );
  }
);

MessageBubble.displayName = 'MessageBubble';
