import type { Message, ChatSession } from '@webchat/core';

export interface ToolCall {
  id: string;
  name: string;
  args?: string;
  result?: string;
  status: 'running' | 'completed';
}

export type TextChunk = { type: 'text'; content: string };
export type ToolCallsChunk = { type: 'toolCalls'; toolCalls: ToolCall[] };
export type ContentChunk = TextChunk | ToolCallsChunk;

export function getContentChunks(message: Message): ContentChunk[] {
  return (message.metadata?.contentChunks as ContentChunk[]) || [];
}

/** Update or append the trailing text chunk. */
export function upsertTextChunk(chunks: ContentChunk[], text: string): ContentChunk[] {
  const lastChunk = chunks[chunks.length - 1];
  if (lastChunk && lastChunk.type === 'text') {
    return [...chunks.slice(0, -1), { type: 'text', content: text }];
  }
  return [...chunks, { type: 'text', content: text }];
}

/** Append a tool-call chunk; returns null when the tool id already exists. */
export function appendToolCallChunk(
  chunks: ContentChunk[],
  toolCall: ToolCall
): ContentChunk[] | null {
  const toolExists = chunks.some(
    (chunk) =>
      chunk.type === 'toolCalls' &&
      chunk.toolCalls.some((tool) => tool.id === toolCall.id)
  );
  if (toolExists) {
    return null;
  }
  return [...chunks, { type: 'toolCalls', toolCalls: [toolCall] }];
}

/** Patch a tool call matched by id across all toolCalls chunks. */
export function patchToolCall(
  chunks: ContentChunk[],
  toolCallId: string,
  patch: Partial<ToolCall>
): ContentChunk[] {
  return chunks.map((chunk) => {
    if (chunk.type !== 'toolCalls') {
      return chunk;
    }
    return {
      ...chunk,
      toolCalls: chunk.toolCalls.map((tool) =>
        tool.id === toolCallId ? { ...tool, ...patch } : tool
      ),
    };
  });
}

export function withUpdatedChunks(
  message: Message,
  chunks: ContentChunk[],
  content?: string
): Message {
  return {
    ...message,
    ...(content !== undefined ? { content } : {}),
    metadata: {
      ...message.metadata,
      contentChunks: chunks,
    },
  };
}

/** Apply a pure chunks transform to React message state for a target id. */
export function mapMessageChunks(
  messages: Message[],
  messageId: string | null,
  transform: (chunks: ContentChunk[], message: Message) => ContentChunk[] | null,
  content?: string
): Message[] {
  if (!messageId) {
    return messages;
  }
  return messages.map((msg) => {
    if (msg.id !== messageId) {
      return msg;
    }
    const nextChunks = transform(getContentChunks(msg), msg);
    if (nextChunks === null) {
      return msg;
    }
    return withUpdatedChunks(msg, nextChunks, content);
  });
}

/** Mutate the in-memory session message chunks to match UI state. */
export function syncSessionChunks(
  session: ChatSession | null | undefined,
  messageId: string | null,
  transform: (chunks: ContentChunk[]) => ContentChunk[] | null,
  content?: string
): void {
  if (!session || !messageId) {
    return;
  }
  const msgIndex = session.messages.findIndex((message) => message.id === messageId);
  if (msgIndex === -1) {
    return;
  }
  const current = session.messages[msgIndex];
  const nextChunks = transform(getContentChunks(current));
  if (nextChunks === null) {
    return;
  }
  session.messages[msgIndex] = withUpdatedChunks(current, nextChunks, content);
}
