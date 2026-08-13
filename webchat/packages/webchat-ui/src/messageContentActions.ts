import {
  extractMessageText,
  type Message,
  type MessageContent,
} from '@webchat/core';

export interface RegenerationPlan {
  preservedMessages: Message[];
  contentToSend: string;
}

export function getMessageCopyText(content: string | MessageContent[]): string {
  return extractMessageText(content);
}

/** Plan regeneration without mutating state; empty captions leave the conversation intact. */
export function planMessageRegeneration(
  messages: Message[],
  messageId: string
): RegenerationPlan | null {
  const messageIndex = messages.findIndex((message) => message.id === messageId);
  if (messageIndex === -1) return null;

  const currentMessage = messages[messageIndex];
  let userMessageIndex = messageIndex;
  if (currentMessage.sender === 'bot') {
    userMessageIndex -= 1;
    while (userMessageIndex >= 0 && messages[userMessageIndex].sender !== 'user') {
      userMessageIndex -= 1;
    }
  }
  if (userMessageIndex < 0) return null;

  const contentToSend = extractMessageText(messages[userMessageIndex].content);
  if (contentToSend.trim().length === 0) return null;

  return {
    preservedMessages: messages.slice(0, userMessageIndex),
    contentToSend,
  };
}
