import { findRegenerationMessage } from '@bk-lite/chat-content/regeneration';
import {
  extractMessageText,
  type Message,
  type MessageContent,
} from '@webchat/core';

export interface RegenerationPlan {
  preservedMessages: Message[];
  contentToSend: string;
  messageToSend: Message;
}

export function getMessageCopyText(content: string | MessageContent[]): string {
  return extractMessageText(content);
}

/** Plan regeneration without mutating state; empty captions leave the conversation intact. */
export function planMessageRegeneration(
  messages: Message[],
  messageId: string
): RegenerationPlan | null {
  const original = findRegenerationMessage(messages, messageId);
  if (!original) return null;
  const contentToSend = extractMessageText(original.content);
  const hasImages = Array.isArray(original.content) && original.content.some(part => part.type === 'image_url');
  const hasAttachments = Array.isArray(original.metadata?.attachments) && original.metadata.attachments.length > 0;
  if (!contentToSend.trim() && !hasImages && !hasAttachments) return null;
  return { preservedMessages: [...messages], contentToSend, messageToSend: original };
}
