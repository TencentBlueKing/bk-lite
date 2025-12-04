/**
 * 消息发送逻辑 Hook
 */

import { useCallback, MutableRefObject } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { CustomChatMessage } from '@/app/opspilot/types/global';

interface UseSendMessageProps {
  loading: boolean;
  token: string | null;
  messages: CustomChatMessage[];
  updateMessages: (updater: CustomChatMessage[] | ((prev: CustomChatMessage[]) => CustomChatMessage[])) => void;
  setLoading: (loading: boolean) => void;
  handleSendMessage?: (message: string, currentMessages?: any[]) => Promise<{ url: string; payload: any } | null>;
  handleSSEStream: (url: string, payload: any, botMessage: CustomChatMessage) => Promise<void>;
  currentBotMessageRef: MutableRefObject<CustomChatMessage | null>;
  t: (key: string) => string;
}

export const useSendMessage = ({
  loading,
  token,
  messages,
  updateMessages,
  setLoading,
  handleSendMessage,
  handleSSEStream,
  currentBotMessageRef,
  t
}: UseSendMessageProps) => {
  
  const sendMessage = useCallback(
    async (content: string, currentMessages?: CustomChatMessage[]) => {
      if (!content || loading || !token) {
        return;
      }

      setLoading(true);

      const newUserMessage: CustomChatMessage = {
        id: uuidv4(),
        content,
        role: 'user',
        createAt: new Date().toISOString(),
        updateAt: new Date().toISOString(),
      };

      const botLoadingMessage: CustomChatMessage = {
        id: uuidv4(),
        content: '',
        role: 'bot',
        createAt: new Date().toISOString(),
        updateAt: new Date().toISOString(),
      };

      // 设置当前 bot 消息引用，用于显示 loading 动画
      currentBotMessageRef.current = botLoadingMessage;

      const messagesToUse = currentMessages || messages;
      const updatedMessages = [...messagesToUse, newUserMessage, botLoadingMessage];
      updateMessages(updatedMessages);

      try {
        if (handleSendMessage) {
          const result = await handleSendMessage(content, messagesToUse);

          if (result === null) {
            updateMessages(messagesToUse);
            setLoading(false);
            return;
          }

          const { url, payload } = result;
          await handleSSEStream(url, payload, botLoadingMessage);
        }
      } catch (error: any) {
        console.error(`${t('chat.sendFailed')}:`, error);

        updateMessages(prevMessages =>
          prevMessages.map(msgItem =>
            msgItem.id === botLoadingMessage.id
              ? { ...msgItem, content: t('chat.connectionError') }
              : msgItem
          )
        );
        setLoading(false);
      }
    },
    [loading, token, messages, handleSendMessage, handleSSEStream, updateMessages, setLoading, currentBotMessageRef, t]
  );

  return { sendMessage };
};
