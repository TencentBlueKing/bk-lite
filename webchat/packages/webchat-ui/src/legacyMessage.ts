import type { MessageContent, MessageType } from '@webchat/core';

const MESSAGE_TYPES: ReadonlySet<string> = new Set([
  'text',
  'image',
  'markdown',
  'html',
  'file',
  'button',
  'multimodal',
]);

export interface LegacyMessage {
  id?: string;
  type: MessageType;
  content: string | MessageContent[];
  metadata?: Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isMessageType(value: unknown): value is MessageType {
  return typeof value === 'string' && MESSAGE_TYPES.has(value);
}

function isMessageContent(value: unknown): value is MessageContent {
  if (!isRecord(value)) return false;

  switch (value.type) {
    case 'text':
      return typeof value.text === 'string';
    case 'message':
      return typeof value.message === 'string';
    case 'image_url':
      return typeof value.image_url === 'string';
    default:
      return false;
  }
}

function isToolCall(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    (value.args === undefined || typeof value.args === 'string') &&
    (value.result === undefined || typeof value.result === 'string') &&
    (value.status === 'running' || value.status === 'completed')
  );
}

function isContentChunk(value: unknown): boolean {
  if (!isRecord(value)) return false;
  if (value.type === 'text') {
    return typeof value.content === 'string';
  }
  if (value.type === 'toolCalls') {
    return Array.isArray(value.toolCalls) && value.toolCalls.every(isToolCall);
  }
  return false;
}

function isMetadata(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) return false;
  return (
    value.contentChunks === undefined ||
    (Array.isArray(value.contentChunks) && value.contentChunks.every(isContentChunk))
  );
}

function isContent(value: unknown): value is string | MessageContent[] {
  return (
    (typeof value === 'string' && value.length > 0) ||
    (Array.isArray(value) && value.length > 0 && value.every(isMessageContent))
  );
}

/** Validate and normalize an untyped legacy SSE message before rendering. */
export function parseLegacyMessage(data: unknown): LegacyMessage | null {
  if (!isRecord(data) || !isContent(data.content)) return null;
  if (data.id !== undefined && (typeof data.id !== 'string' || data.id.length === 0)) return null;
  const type = data.type ?? 'text';
  if (!isMessageType(type)) return null;
  if (data.metadata !== undefined && !isMetadata(data.metadata)) return null;

  return {
    ...(typeof data.id === 'string' ? { id: data.id } : {}),
    type,
    content: data.content,
    ...(data.metadata !== undefined ? { metadata: data.metadata } : {}),
  };
}
