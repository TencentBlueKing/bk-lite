import React, { useState, type ComponentPropsWithoutRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import { Message, type MessageContent } from '@webchat/core';
import { MessageActions } from './MessageActions';
import { ConfirmDialog } from './ConfirmDialog';
import { ImagePreview } from './ImagePreview';
import { ToolCallDisplay, type ToolCall } from './ToolCallDisplay';
import { ThinkingPanel } from './ThinkingPanel';
import { WC } from '../chrome';

const markdownPlugins = {
  remarkPlugins: [remarkGfm],
  rehypePlugins: [rehypeSanitize],
};

const markdownClassName =
  'max-w-none break-words text-sm leading-[1.7] [&_h1]:mb-2 [&_h1]:mt-3 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:mb-1 [&_h3]:mt-2 [&_h3]:font-semibold [&_p]:my-1.5 [&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-0.5 [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:p-3 [&_pre]:bg-[var(--color-code-block-bg,var(--color-fill-1,#f6f8f9))] [&_pre]:text-[var(--color-code-block-text,var(--color-text-1,#1e252e))] [&_code]:rounded [&_code]:px-1 [&_code]:bg-[var(--color-code-block-bg,var(--color-fill-1,#f6f8f9))] [&_a]:text-[var(--color-primary,#155AEF)] [&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--color-border-1,#edeff3)] [&_blockquote]:pl-3 [&_hr]:my-3';

const userBubbleStyle: React.CSSProperties = {
  background: WC.botBubble,
  color: WC.botText,
  border: `1px solid ${WC.botBorder}`,
  borderRadius: 16,
  borderBottomRightRadius: 4,
};

interface MessageBubbleProps {
  message: Message;
  isLastBotMessage?: boolean;
  fillWidth?: boolean;
  onRegenerate?: (messageId: string) => void;
  onCopy?: (content: string) => void;
  onDelete?: (messageId: string) => void;
}

type ContentChunk = 
  | { type: 'text'; content: string }
  | { type: 'toolCalls'; toolCalls: ToolCall[] };

type CodeBlockProps = ComponentPropsWithoutRef<'code'> & {
  inline?: boolean;
  node?: unknown;
};

// Custom code block renderer with syntax highlighting
const CodeBlock = ({ inline, className, children, style, ...props }: CodeBlockProps) => {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';

  return !inline && language ? (
    <pre
      className="my-2 overflow-x-auto rounded-md p-3 text-sm leading-6"
      style={style}
    >
      <code className={className} {...props}>
        {String(children).replace(/\n$/, '')}
      </code>
    </pre>
  ) : (
    <code className={className} style={style} {...props}>
      {children}
    </code>
  );
};

export const MessageBubble: React.FC<MessageBubbleProps> = React.memo(
  ({ message, isLastBotMessage, fillWidth, onRegenerate, onCopy, onDelete }) => {
    const isBot = message.sender === 'bot';
    const [showActions, setShowActions] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null);
    
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
          {message.content.map((item: MessageContent, index: number) => {
            const imageUrl = item.image_url;
            const unpreviewedImageIndexes = Array.isArray(message.metadata?.unpreviewedImageIndexes)
              ? message.metadata.unpreviewedImageIndexes
              : [];
            if (item.type === 'image_url' && imageUrl) {
              if (unpreviewedImageIndexes.includes(index)) {
                return (
                  <div
                    key={`img-${index}`}
                    role="status"
                    aria-label="图片已发送（格式未在浏览器解码预览）"
                  >
                    <p className="rounded-md px-2 py-1 text-xs text-[var(--color-text-3,#86909c)]">
                      图片已发送（格式未在浏览器解码预览）
                    </p>
                  </div>
                );
              }
              return (
                <div key={`img-${index}`} className="max-w-xs">
                  <img 
                    src={imageUrl}
                    alt={`Image ${index + 1}`}
                    className="h-auto w-full cursor-pointer rounded-md border border-[var(--color-border-1,#e8eaf0)] hover:opacity-90"
                    onClick={() => setPreviewImage({ src: imageUrl, alt: `Image ${index + 1}` })}
                  />
                </div>
              );
            } else if (item.type === 'message' && item.message) {
              return (
                <div key={`msg-${index}`} className={markdownClassName}>
                  <ReactMarkdown
                    {...markdownPlugins}
                    components={{
                      code: CodeBlock
                    }}
                  >
                    {item.message}
                  </ReactMarkdown>
                </div>
              );
            } else if (item.type === 'text' && item.text) {
              return (
                <div key={`text-${index}`} className={markdownClassName}>
                  <ReactMarkdown
                    {...markdownPlugins}
                    components={{
                      code: CodeBlock
                    }}
                  >
                    {item.text}
                  </ReactMarkdown>
                </div>
              );
            }
            return null;
          })}
        </div>
      );
    };

    const columnClass = isBot
      ? 'min-w-0 flex-1'
      : fillWidth
        ? 'max-w-[92%]'
        : 'max-w-[78%]';

    const renderMarkdown = (source: string) => (
      <div className={markdownClassName}>
        <ReactMarkdown
          {...markdownPlugins}
          components={{
            code: CodeBlock
          }}
        >
          {source}
        </ReactMarkdown>
      </div>
    );

    const renderBotAnswer = (children: React.ReactNode, key?: string) => (
      <div
        key={key}
        className="w-full text-sm leading-[1.7]"
        style={{ color: WC.botText }}
      >
        {children}
      </div>
    );

    const botColumn = (
      <div className={`flex min-w-0 flex-col gap-2 ${columnClass}`}>
        <ThinkingPanel
          thinking={typeof message.metadata?.thinking === 'string' ? message.metadata.thinking : undefined}
          isThinking={Boolean(message.metadata?.isThinking)}
        />
        {groupedChunks.length > 0
          ? groupedChunks.map((chunk, index) => {
              if (chunk.type === 'text') {
                return renderBotAnswer(renderMarkdown(chunk.content), `text-${index}`);
              }
              if (chunk.type === 'toolCalls') {
                return <ToolCallDisplay key={`tool-${index}`} toolCalls={chunk.toolCalls} />;
              }
              return null;
            })
          : hasContent
            ? renderBotAnswer(renderMarkdown(message.content as string))
            : null}
      </div>
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
          <div className={`flex w-full items-start ${isBot ? 'justify-start' : 'flex-row-reverse justify-start'}`}>
            {isBot ? (
              botColumn
            ) : (
              <div
                className={`px-3.5 py-2 text-sm leading-[1.55] ${columnClass}`}
                style={userBubbleStyle}
              >
                {message.type === 'multimodal' ? (
                  renderMultimodalContent()
                ) : (
                  <p className="whitespace-pre-wrap break-words">{message.content as string}</p>
                )}
              </div>
            )}
          </div>
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
        {previewImage && (
          <ImagePreview
            src={previewImage.src}
            alt={previewImage.alt}
            onClose={() => setPreviewImage(null)}
          />
        )}
      </>
    );
  }
);

MessageBubble.displayName = 'MessageBubble';
