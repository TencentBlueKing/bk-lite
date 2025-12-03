import { useCallback } from 'react';
import { Message, SessionManager } from '@webchat/core';

interface UseMessageHandlersProps {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  sessionManagerRef: React.MutableRefObject<SessionManager | null>;
  handleSendMessage: (content: string) => Promise<void>;
}

export const useMessageHandlers = ({
  messages,
  setMessages,
  sessionManagerRef,
  handleSendMessage,
}: UseMessageHandlersProps) => {
  // Handle message regeneration
  const handleRegenerate = useCallback(
    (messageId: string) => {
      const messageIndex = messages.findIndex((msg) => msg.id === messageId);
      if (messageIndex === -1) return;

      const currentMessage = messages[messageIndex];
      let userMessageIndex = -1;

      // If current message is a bot message, find the user message before it
      if (currentMessage.sender === 'bot') {
        userMessageIndex = messageIndex - 1;
        while (userMessageIndex >= 0 && messages[userMessageIndex].sender !== 'user') {
          userMessageIndex--;
        }
      }
      // If current message is a user message, it's the one we want to regenerate
      else {
        userMessageIndex = messageIndex;
      }

      if (userMessageIndex >= 0) {
        const userMessage = messages[userMessageIndex];
        // Keep all messages before the user message, remove the user message and everything after
        setMessages((prev) => prev.slice(0, userMessageIndex));

        // Update session storage
        if (sessionManagerRef.current) {
          const newMessages = messages.slice(0, userMessageIndex);
          const session = sessionManagerRef.current.getSession();
          if (session) {
            session.messages = newMessages;
            sessionManagerRef.current.clearSession();
            sessionManagerRef.current.initSession();
            newMessages.forEach((msg) => sessionManagerRef.current?.addMessage(msg));
          }
        }

        // Resend the user message
        setTimeout(() => handleSendMessage(userMessage.content), 100);
      }
    },
    [messages, handleSendMessage, setMessages, sessionManagerRef]
  );

  // Handle message copy
  const handleCopy = useCallback(() => {
    // Optional: show a toast notification
    console.log('Message copied to clipboard');
  }, []);

  // Handle message deletion
  const handleDelete = useCallback(
    (messageId: string) => {
      setMessages((prev) => {
        const newMessages = prev.filter((msg) => msg.id !== messageId);
        // Update session storage with new messages
        if (sessionManagerRef.current) {
          const session = sessionManagerRef.current.getSession();
          if (session) {
            session.messages = newMessages;
            // Force save by clearing and re-adding all messages
            sessionManagerRef.current.clearSession();
            sessionManagerRef.current.initSession();
            newMessages.forEach((msg) => sessionManagerRef.current?.addMessage(msg));
          }
        }
        return newMessages;
      });
    },
    [setMessages, sessionManagerRef]
  );

  return {
    handleRegenerate,
    handleCopy,
    handleDelete,
  };
};
