import React from 'react';

export { ChatContentProvider, useChatContentHost } from '../../web/packages/chat-content/src/host';

export function ChatMarkdown({ content }: { content: string }) {
  return <div>{content}</div>;
}
