'use client';

import dynamic from 'next/dynamic';

const FloatingButton = dynamic(
  () => import('@webchat/ui').then((module) => module.FloatingButton),
  { ssr: false }
);

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
