/**
 * 消息发送逻辑 Hook
 */

import { useCallback, MutableRefObject } from 'react';
import { message as antMessage } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import { CustomChatMessage } from '@/app/opspilot/types/global';

interface UseSendMessageProps {
  loading: boolean;
  token: string | null;
  messages: CustomChatMessage[];
  updateMessages: (updater: CustomChatMessage[] | ((prev: CustomChatMessage[]) => CustomChatMessage[])) => void;
  setLoading: (loading: boolean) => void;
  handleSendMessage?: (message: string, currentMessages?: any[], userMessage?: CustomChatMessage) => Promise<{
    url: string;
    payload: any;
    interruptRequest?: {
      enabled: boolean;
      url: string;
      reason?: string;
    };
  } | null>;
  handleSSEStream: (url: string, payload: any, botMessage: CustomChatMessage, interruptRequest?: {
    enabled: boolean;
    url: string;
    reason?: string;
  }, onAccepted?: () => void) => Promise<void>;
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
    async (
      content: string,
      currentMessages?: CustomChatMessage[],
      attachments?: any[],
      choice?: { choiceId?: string; optionKey?: string; selectedKeys?: string[]; replyToChoiceId?: string },
    ) => {
      if ((!content && !attachments?.length) || loading || !token) {
        return;
      }

      setLoading(true);

      const newUserMessage: CustomChatMessage = {
        id: uuidv4(),
        content,
        role: 'user',
        createAt: new Date().toISOString(),
        updateAt: new Date().toISOString(),
        ...(attachments && attachments.length > 0 && { attachments }),
        ...(choice?.choiceId ? { choiceId: choice.choiceId, choiceOption: choice.optionKey || '' } : {}),
        ...(choice?.replyToChoiceId ? { replyToChoiceId: choice.replyToChoiceId } : {}),
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
      // 用函数式更新追加，避免绝对数组覆盖正在流式写入的正文
      const appendTurn = () => updateMessages(prev => {
        const last = prev[prev.length - 1];
        if (!choice?.choiceId || !choice.optionKey || !last?.userChoiceRequests) {
          return [...prev, newUserMessage, botLoadingMessage];
        }
        const selected = choice.selectedKeys || [choice.optionKey];
        const requests = last.userChoiceRequests.map(card => card.choice_id === choice.choiceId
          ? { ...card, status: 'submitted' as const, selected } : card);
        return [...prev.slice(0, -1), { ...last, userChoiceRequests: requests }, newUserMessage, botLoadingMessage];
      });
      const answeringChoice = Boolean(choice?.choiceId || choice?.replyToChoiceId);
      if (!answeringChoice) appendTurn();

      try {
        if (handleSendMessage) {
          const result = await handleSendMessage(content, messagesToUse, newUserMessage);

          if (result === null) {
            updateMessages(prev => prev.filter(
              msg => msg.id !== newUserMessage.id && msg.id !== botLoadingMessage.id
            ));
            setLoading(false);
            return;
          }

          const { url, payload, interruptRequest } = result;
          await handleSSEStream(url, payload, botLoadingMessage, interruptRequest, answeringChoice ? appendTurn : undefined);
        }
      } catch (error: any) {
        if (answeringChoice) {
          antMessage.error(t('chat.sendFailed'));
          setLoading(false);
          return;
        }
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
