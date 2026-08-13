import { useCallback, useEffect, useRef } from 'react';
import { Message, SessionManager } from '@webchat/core';
import { planMessageRegeneration } from '../messageContentActions';

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
  const messagesRef = useRef(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Handle message regeneration
  const handleRegenerate = useCallback(
    (messageId: string) => {
      const currentMessages = messagesRef.current;
      const plan = planMessageRegeneration(currentMessages, messageId);
      if (plan) {
        setMessages(plan.preservedMessages);

        // Update session storage
        if (sessionManagerRef.current) {
          const session = sessionManagerRef.current.getSession();
          if (session) {
            session.messages = plan.preservedMessages;
            sessionManagerRef.current.clearSession();
            sessionManagerRef.current.initSession();
            plan.preservedMessages.forEach((msg) =>
              sessionManagerRef.current?.addMessage(msg)
            );
          }
        }

        setTimeout(() => handleSendMessage(plan.contentToSend), 100);
      }
    },
    [handleSendMessage, setMessages, sessionManagerRef]
  );

  // Handle message copy
  const handleCopy = useCallback(() => {
    // Clipboard write is handled by MessageActions; hook kept for API symmetry.
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
