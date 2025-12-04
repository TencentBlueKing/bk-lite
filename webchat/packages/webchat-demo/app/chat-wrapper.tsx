'use client';

import { FloatingButton } from '@webchat/ui';

export function ChatWrapper() {
  const sseUrl = typeof window !== 'undefined' 
    ? `${window.location.origin}/api/chat`
    : 'http://localhost:3000/api/chat';

  return (
    <FloatingButton
      sseUrl={sseUrl}
      theme="light"
    />
  );
}
