/**
 * SSE 流处理 Hook
 */

import { useCallback, useRef } from 'react';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import { AGUIMessage, SSEChunk } from '@/app/opspilot/types/chat';
import { AGUIMessageHandler } from '../aguiMessageHandler';
import { ToolCallInfo } from '../toolCallRenderer';

interface UseSSEStreamProps {
  token: string | null;
  useAGUIProtocol: boolean;
  updateMessages: (updater: (prev: CustomChatMessage[]) => CustomChatMessage[]) => void;
  setLoading: (loading: boolean) => void;
  t: (key: string) => string;
}

export const useSSEStream = ({
  token,
  useAGUIProtocol,
  updateMessages,
  setLoading,
  t
}: UseSSEStreamProps) => {
  const abortControllerRef = useRef<AbortController | null>(null);
  const toolCallsRef = useRef<Map<string, ToolCallInfo>>(new Map());

  const stopSSEConnection = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLoading(false);
  }, [setLoading]);

  const handleSSEStream = useCallback(
    async (url: string, payload: any, botMessage: CustomChatMessage) => {
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      try {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };

        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(url, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
          credentials: 'include',
          signal: abortController.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('Failed to get response reader');
        }

        const decoder = new TextDecoder();
        let buffer = '';
        
        // 创建一个持久的 Handler 实例，避免 accumulatedContent 被重置
        const handler = new AGUIMessageHandler(
          botMessage,
          updateMessages,
          toolCallsRef.current
        );
        
        // OpenAI SSE 格式的累积内容
        let accumulatedContent = '';

        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          const chunk = decoder.decode(value, { stream: true });
          buffer += chunk;

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmedLine = line.trim();
            if (trimmedLine === '') continue;

            if (trimmedLine.startsWith('data: ')) {
              const dataStr = trimmedLine.slice(6).trim();

              if (dataStr === '[DONE]') {
                setLoading(false);
                return;
              }

              try {
                const parsedData: any = JSON.parse(dataStr);

                if (useAGUIProtocol && parsedData.type) {
                  const aguiData: AGUIMessage = parsedData;

                  // 使用同一个 handler 实例处理所有消息
                  const shouldStop = handler.handle(aguiData);

                  if (shouldStop) {
                    toolCallsRef.current.clear();
                    setLoading(false);
                    return;
                  }
                } else {
                  // OpenAI SSE format
                  const sseData: SSEChunk = parsedData;

                  if (sseData.choices && sseData.choices.length > 0) {
                    const choice = sseData.choices[0];

                    if (choice.finish_reason === 'stop') {
                      setLoading(false);
                      return;
                    }

                    if (choice.delta && choice.delta.content) {
                      accumulatedContent += choice.delta.content;

                      updateMessages(prevMessages =>
                        prevMessages.map(msgItem =>
                          msgItem.id === botMessage.id
                            ? {
                              ...msgItem,
                              content: accumulatedContent,
                              updateAt: new Date().toISOString()
                            }
                            : msgItem
                        )
                      );
                    }
                  }
                }
              } catch (parseError) {
                console.warn('Failed to parse SSE chunk:', dataStr, parseError);
                continue;
              }
            }
          }
        }
      } catch (error: any) {
        if (error.name === 'AbortError') {
          return;
        }

        console.error('SSE stream error:', error);

        updateMessages(prevMessages =>
          prevMessages.map(msgItem =>
            msgItem.id === botMessage.id
              ? { ...msgItem, content: `${t('chat.connectionError')}: ${error.message}` }
              : msgItem
          )
        );
      } finally {
        setLoading(false);
        abortControllerRef.current = null;
      }
    },
    [token, updateMessages, useAGUIProtocol, setLoading, t]
  );

  return {
    handleSSEStream,
    stopSSEConnection,
    toolCallsRef
  };
};
