import React, { useState } from 'react';
import { Bubble } from '@ant-design/x';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '@webchat/core';
import { MessageActions } from './MessageActions';
import { ConfirmDialog } from './ConfirmDialog';
import { ToolCallDisplay, type ToolCall } from './ToolCallDisplay';

interface MessageBubbleProps {
  message: Message;
  botAvatar: React.ReactElement;
  userAvatar: React.ReactElement;
  isLastBotMessage?: boolean;
  onRegenerate?: (messageId: string) => void;
  onCopy?: (content: string) => void;
  onDelete?: (messageId: string) => void;
}

type ContentChunk = 
  | { type: 'text'; content: string }
  | { type: 'toolCalls'; toolCalls: ToolCall[] };

export const MessageBubble: React.FC<MessageBubbleProps> = (
  ({ message, botAvatar, userAvatar, isLastBotMessage, onRegenerate, onCopy, onDelete }) => {
    const isBot = message.sender === 'bot';
    const [showActions, setShowActions] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    
    // Get content chunks from message metadata (ordered mix of text and tool calls)
    const contentChunks = (message.metadata?.contentChunks as ContentChunk[]) || [];
    
    // Determine what to render
    const hasChunks = contentChunks.length > 0;
    const hasContent = message.content && typeof message.content === 'string' && message.content.trim().length > 0;
    
    // Group consecutive tool chunks together
    const groupedChunks: Array<{ type: 'text'; content: string } | { type: 'toolCalls'; toolCalls: ToolCall[] }> = [];
    if (hasChunks) {
      contentChunks.forEach((chunk) => {
        if (chunk.type === 'toolCalls' && chunk.toolCalls.length > 0) {
          // Find the last group and merge if it's also toolCalls
          const lastGroup = groupedChunks[groupedChunks.length - 1];
          if (lastGroup && lastGroup.type === 'toolCalls') {
            lastGroup.toolCalls.push(...chunk.toolCalls);
          } else {
            groupedChunks.push({ type: 'toolCalls', toolCalls: [...chunk.toolCalls] });
          }
        } else if (chunk.type === 'text' && chunk.content && chunk.content.trim()) {
          groupedChunks.push({ type: 'text', content: chunk.content });
        }
      });
    }
    
    // Render multimodal content (images + text)
    const renderMultimodalContent = () => {
      if (typeof message.content !== 'object' || !Array.isArray(message.content)) {
        return null;
      }

      return (
        <div className="space-y-2">
          {message.content.map((item: any, index: number) => {
            if (item.type === 'image_url' && item.image_url) {
              return (
                <div key={`img-${index}`} className="max-w-xs">
                  <img 
                    src={item.image_url} 
                    alt={`Image ${index + 1}`}
                    className="rounded border border-gray-200 w-full h-auto"
                  />
                </div>
              );
            } else if (item.type === 'message' && item.message) {
              return (
                <div key={`msg-${index}`} className="prose prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.message}</ReactMarkdown>
                </div>
              );
            } else if (item.type === 'text' && item.text) {
              return (
                <div key={`text-${index}`} className="prose prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
                </div>
              );
            }
            return null;
          })}
        </div>
      );
    };

    const content = isBot ? (
      <div>
        {groupedChunks.length > 0 ? (
          // Render grouped chunks in order
          groupedChunks.map((chunk, index) => {
            if (chunk.type === 'text') {
              return (
                <div key={`text-${index}`} className="prose prose-sm max-w-none prose-pre:bg-gray-100 prose-pre:text-gray-900 prose-hr:my-3 prose-h1:mt-3 prose-h1:mb-2 prose-h2:mt-3 prose-h2:mb-2 prose-h3:mt-2 prose-h3:mb-1 prose-h4:mt-2 prose-h4:mb-1 prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{chunk.content}</ReactMarkdown>
                </div>
              );
            } else if (chunk.type === 'toolCalls') {
              return (
                <div key={`tool-${index}`} className="my-2">
                  <ToolCallDisplay toolCalls={chunk.toolCalls} />
                </div>
              );
            }
            return null;
          })
        ) : hasContent ? (
          // Fallback to display content if no chunks (for backward compatibility)
          <div className="prose prose-sm max-w-none prose-pre:bg-gray-100 prose-pre:text-gray-900 prose-hr:my-3 prose-h1:mt-3 prose-h1:mb-2 prose-h2:mt-3 prose-h2:mb-2 prose-h3:mt-2 prose-h3:mb-1 prose-h4:mt-2 prose-h4:mb-1 prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content as string}</ReactMarkdown>
          </div>
        ) : null}
      </div>
    ) : (
      // User message - check if multimodal
      message.type === 'multimodal' ? renderMultimodalContent() : (message.content as string)
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
