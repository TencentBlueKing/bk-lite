/**
 * SSE 流处理 Hook
 */

import { useCallback, useRef } from 'react';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import { AGUIMessage, SSEChunk } from '@/app/opspilot/types/chat';
import { AGUIMessageHandler } from '../aguiMessageHandler';
import { ToolCallInfo } from '../toolCallRenderer';
import type { LlmContextUsage } from '../llmContextUsage';

interface UseSSEStreamProps {
  token: string | null;
  useAGUIProtocol: boolean;
  updateMessages: (updater: (prev: CustomChatMessage[]) => CustomChatMessage[]) => void;
  setLoading: (loading: boolean) => void;
  t: (key: string) => string;
  onCancelCleanup?: () => void;
  onContextUsage?: (usage: LlmContextUsage) => void;
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
  onContextUsage,
}: UseSSEStreamProps) => {
  const abortControllerRef = useRef<AbortController | null>(null);
  const toolCallsRef = useRef<Map<string, ToolCallInfo>>(new Map());
  const latestExecutionIdRef = useRef<string>('');
  const interruptRequestRef = useRef<InterruptRequestConfig | null>(null);
  const isStreamActiveRef = useRef(false);
  const tokenRef = useRef(token);
  const onCancelCleanupRef = useRef(onCancelCleanup);
  const onContextUsageRef = useRef(onContextUsage);
  tokenRef.current = token;
  onCancelCleanupRef.current = onCancelCleanup;
  onContextUsageRef.current = onContextUsage;

  const stopSSEConnection = useCallback(() => {
    const currentExecutionId = latestExecutionIdRef.current;
    const currentInterruptRequest = interruptRequestRef.current;
    const wasActive = isStreamActiveRef.current || Boolean(abortControllerRef.current);
    const shouldInterrupt = wasActive && currentInterruptRequest?.enabled && currentExecutionId;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    isStreamActiveRef.current = false;
    setLoading(false);
    // 仅在真实中断活跃流时清理；effect 依赖抖动不得清空已流出内容
    if (wasActive) {
      onCancelCleanupRef.current?.();
    }

    const authToken = tokenRef.current;
    if (shouldInterrupt && authToken) {
      void fetch(currentInterruptRequest.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
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
  }, [setLoading]);

  const handleSSEStream = useCallback(
    async (url: string, payload: any, botMessage: CustomChatMessage, interruptRequest?: InterruptRequestConfig) => {
      const abortController = new AbortController();
      abortControllerRef.current = abortController;
      interruptRequestRef.current = interruptRequest || null;
      latestExecutionIdRef.current = '';
      isStreamActiveRef.current = true;
      let handler: AGUIMessageHandler | null = null;
      let streamCloseReason = t('chat.connectionError');
      let streamTerminal: 'open' | 'complete' | 'abort' | 'error' = 'open';
      let accumulatedContent = '';

      try {
        const headers: Record<string, string> = {
          Accept: 'text/event-stream',
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
        handler = new AGUIMessageHandler(
          botMessage,
          updateMessages,
          toolCallsRef.current,
          (usage) => onContextUsageRef.current?.(usage)
        );
        
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
                streamTerminal = 'complete';
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
                    streamTerminal = 'complete';
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
                      streamTerminal = 'complete';
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
          streamTerminal = 'abort';
          return;
        }

        console.error('SSE stream error:', error);
        streamTerminal = 'error';
        streamCloseReason = `${t('chat.connectionError')}: ${error.message}`;
        if (!handler) {
          updateMessages(prevMessages =>
            prevMessages.map(msgItem =>
              msgItem.id === botMessage.id
                ? { ...msgItem, content: streamCloseReason, isStreamingTools: false }
                : msgItem
            )
          );
        }
      } finally {
        if (handler) {
          if (!useAGUIProtocol && accumulatedContent) {
            handler.seedPlainText(accumulatedContent);
          }
          if (streamTerminal === 'complete') {
            handler.completeStream();
          } else if (streamTerminal === 'abort') {
            handler.abortStream();
          } else {
            handler.handleStreamClosed(streamCloseReason);
          }
        }
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
