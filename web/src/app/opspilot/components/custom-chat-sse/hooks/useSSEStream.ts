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
  onCancelCleanup?: () => void;
}

interface InterruptRequestConfig {
  enabled: boolean;
  url: string;
  reason?: string;
}

const extractExecutionId = (payload: unknown): string => {
  if (!payload || typeof payload !== 'object') {
    return '';
  }

  const record = payload as Record<string, unknown>;
  const directExecutionId = record.execution_id;
  if (typeof directExecutionId === 'string' && directExecutionId) {
    return directExecutionId;
  }

  const threadId = record.threadId;
  if (typeof threadId === 'string' && threadId) {
    return threadId;
  }

  const runId = record.runId;
  if (typeof runId === 'string' && runId) {
    return runId;
  }

  return '';
};

export const useSSEStream = ({
  token,
  useAGUIProtocol,
  updateMessages,
  setLoading,
  t,
  onCancelCleanup,
}: UseSSEStreamProps) => {
  const abortControllerRef = useRef<AbortController | null>(null);
  const toolCallsRef = useRef<Map<string, ToolCallInfo>>(new Map());
  const latestExecutionIdRef = useRef<string>('');
  const interruptRequestRef = useRef<InterruptRequestConfig | null>(null);
  const isStreamActiveRef = useRef(false);

  const stopSSEConnection = useCallback(() => {
    const currentExecutionId = latestExecutionIdRef.current;
    const currentInterruptRequest = interruptRequestRef.current;
    const shouldInterrupt = isStreamActiveRef.current && currentInterruptRequest?.enabled && currentExecutionId;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    isStreamActiveRef.current = false;
    setLoading(false);
    onCancelCleanup?.();

    if (shouldInterrupt && token) {
      void fetch(currentInterruptRequest.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        credentials: 'include',
        body: JSON.stringify({
          execution_id: currentExecutionId,
          reason: currentInterruptRequest.reason || 'user_manual',
        }),
      }).catch((error) => {
        console.warn('Failed to interrupt execution:', error);
      });
    }
  }, [onCancelCleanup, setLoading, token]);

  const handleSSEStream = useCallback(
    async (url: string, payload: any, botMessage: CustomChatMessage, interruptRequest?: InterruptRequestConfig) => {
      const abortController = new AbortController();
      abortControllerRef.current = abortController;
      interruptRequestRef.current = interruptRequest || null;
      latestExecutionIdRef.current = '';
      isStreamActiveRef.current = true;

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

        const executionId = response.headers.get('X-Execution-ID');
        if (executionId) {
          latestExecutionIdRef.current = executionId;
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
                isStreamActiveRef.current = false;
                setLoading(false);
                return;
              }

              try {
                const parsedData: any = JSON.parse(dataStr);
                const parsedExecutionId = extractExecutionId(parsedData);
                if (parsedExecutionId && !latestExecutionIdRef.current) {
                  latestExecutionIdRef.current = parsedExecutionId;
                }

                if (useAGUIProtocol && parsedData.type) {
                  const aguiData: AGUIMessage = parsedData;

                  // 使用同一个 handler 实例处理所有消息
                  const shouldStop = handler.handle(aguiData);

                  if (shouldStop) {
                    toolCallsRef.current.clear();
                    isStreamActiveRef.current = false;
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
        isStreamActiveRef.current = false;
        setLoading(false);
        abortControllerRef.current = null;
        interruptRequestRef.current = null;
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
