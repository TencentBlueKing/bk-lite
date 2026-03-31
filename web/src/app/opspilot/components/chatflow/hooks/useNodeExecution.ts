import { useEffect, useCallback, useState, useRef } from 'react';
import { message } from 'antd';
import { useSession } from 'next-auth/react';
import { useAuth } from '@/context/auth';
import { useStudioApi } from '../../../api/studio';
import type { WorkflowExecutionDetailItem } from '@/app/opspilot/types/studio';
import { AGUIMessage, BrowserTaskReceivedValue } from '@/app/opspilot/types/chat';
import { ToolCallInfo, syncActiveToolCallPanel, closeActiveToolCallPanel } from '../../custom-chat-sse/toolCallRenderer';

export interface NodeExecutionResult {
  isSSE: boolean;
  content: string;
  toolCalls?: Map<string, ToolCallInfo>;
  rawResponse?: any;
  error?: string;
}

export interface ExecutionSummary {
  status: 'idle' | 'running' | 'success' | 'failed';
  title?: string;
  reason?: string | null;
}

const EXECUTION_POLL_BASE_INTERVAL = 3000;
const EXECUTION_POLL_SLOW_INTERVAL = 6000;

const findExecutionField = (value: unknown, field: string, depth = 0): string | null => {
  if (!value || depth > 3) {
    return null;
  }

  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const directValue = record[field];
    if (typeof directValue === 'string' && directValue) {
      return directValue;
    }

    for (const nestedValue of Object.values(record)) {
      const result = findExecutionField(nestedValue, field, depth + 1);
      if (result) {
        return result;
      }
    }
  }

  return null;
};

export const useNodeExecution = (t: any, initialExecutionId?: string | null) => {
  const { getExecuteWorkflowSSEUrl, fetchExecutionDetail } = useStudioApi();

  const { data: session } = useSession();
  const authContext = useAuth();
  const token = (session?.user as any)?.token || authContext?.token || null;

  const [isExecuteDrawerVisible, setIsExecuteDrawerVisible] = useState(false);
  const [executeNodeId, setExecuteNodeId] = useState<string>('');
  const [executeMessage, setExecuteMessage] = useState<string>('');
  const [executeResult, setExecuteResult] = useState<NodeExecutionResult | null>(null);
  const [executeLoading, setExecuteLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [executionDetailLoading, setExecutionDetailLoading] = useState(false);
  const [executionDetails, setExecutionDetails] = useState<WorkflowExecutionDetailItem[]>([]);
  const [latestExecutionId, setLatestExecutionId] = useState('');
  const [executionSummary, setExecutionSummary] = useState<ExecutionSummary>({ status: 'idle' });
  const [activeExecutionNodeId, setActiveExecutionNodeId] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const toolCallsRef = useRef<Map<string, ToolCallInfo>>(new Map());
  const executionPollTimerRef = useRef<number | null>(null);
  const latestExecutionIdRef = useRef('');
  const fetchExecutionDetailRef = useRef(fetchExecutionDetail);
  const executionSnapshotRef = useRef('');
  const unchangedPollCountRef = useRef(0);
  const tRef = useRef(t);
  const executeNodeIdRef = useRef('');
  const executionRequestInFlightRef = useRef(false);
  const pollingExecutionIdRef = useRef('');

  useEffect(() => {
    fetchExecutionDetailRef.current = fetchExecutionDetail;
  }, [fetchExecutionDetail]);

  useEffect(() => {
    tRef.current = t;
  }, [t]);

  useEffect(() => {
    executeNodeIdRef.current = executeNodeId;
  }, [executeNodeId]);

  const stopExecutionPolling = useCallback(() => {
    if (executionPollTimerRef.current) {
      window.clearTimeout(executionPollTimerRef.current);
      executionPollTimerRef.current = null;
    }
    pollingExecutionIdRef.current = '';
  }, []);

  const openPreviewPanel = useCallback(() => {
    setIsPreviewOpen(true);
  }, []);

  const closePreviewPanel = useCallback(() => {
    setIsPreviewOpen(false);
  }, []);

  const applyExecutionMeta = useCallback((payload: unknown) => {
    const executionId = findExecutionField(payload, 'execution_id');
    if (executionId) {
      latestExecutionIdRef.current = executionId;
      setLatestExecutionId(executionId);
    }
  }, []);

  useEffect(() => {
    const handleExecuteNode = (event: any) => {
      const { nodeId } = event.detail;
      setExecuteNodeId(nodeId);
      setExecuteMessage('');
      setExecuteResult(null);
      setStreamingContent('');
      toolCallsRef.current.clear();
      setIsExecuteDrawerVisible(true);
    };

    window.addEventListener('executeNode', handleExecuteNode);
    return () => {
      window.removeEventListener('executeNode', handleExecuteNode);
    };
  }, []);

  useEffect(() => {
    if (!initialExecutionId || initialExecutionId === latestExecutionIdRef.current) {
      return;
    }

    latestExecutionIdRef.current = initialExecutionId;
    pollingExecutionIdRef.current = initialExecutionId;
    executionSnapshotRef.current = '';
    unchangedPollCountRef.current = 0;
    setLatestExecutionId(initialExecutionId);
    setIsPreviewOpen(true);
    setExecutionSummary({
      status: 'running',
      title: tRef.current('chatflow.preview.running'),
    });
  }, [initialExecutionId]);

  const stopExecution = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setExecuteLoading(false);
  }, []);

  const handleAGUIMessage = useCallback((aguiData: AGUIMessage, contentRef: { current: string }) => {
    applyExecutionMeta(aguiData);

    const findLatestCallingToolCallId = (preferredToolName?: string) => {
      const entries = Array.from(toolCallsRef.current.entries()).reverse();

      if (preferredToolName) {
        const matchedEntry = entries.find(([, toolCall]) => toolCall.status === 'calling' && toolCall.name === preferredToolName);
        if (matchedEntry) {
          return matchedEntry[0];
        }
      }

      const latestCallingEntry = entries.find(([, toolCall]) => toolCall.status === 'calling');
      return latestCallingEntry?.[0];
    };

    switch (aguiData.type) {
      case 'RUN_STARTED':
        setExecutionSummary({
          status: 'running',
          title: t('chatflow.preview.running'),
        });
        break;

      case 'TEXT_MESSAGE_CONTENT':
        if (aguiData.delta) {
          contentRef.current += aguiData.delta;
          setStreamingContent(contentRef.current);
        }
        break;

      case 'TOOL_CALL_START':
        if (aguiData.toolCallId && aguiData.toolCallName) {
          toolCallsRef.current.set(aguiData.toolCallId, {
            name: aguiData.toolCallName,
            args: '',
            status: 'calling'
          });
        }
        break;

      case 'TOOL_CALL_ARGS':
        if (aguiData.toolCallId && aguiData.delta) {
          const toolCall = toolCallsRef.current.get(aguiData.toolCallId);
          if (toolCall) {
            toolCall.args += aguiData.delta;
          }
        }
        break;

      case 'TOOL_CALL_RESULT':
        if (aguiData.toolCallId && aguiData.content) {
          const toolCall = toolCallsRef.current.get(aguiData.toolCallId);
          if (toolCall) {
            toolCall.status = 'completed';
            toolCall.result = aguiData.content;
            closeActiveToolCallPanel(aguiData.toolCallId);
          }
        }
        break;

      case 'CUSTOM':
        if (aguiData.name === 'browser_task_received' && aguiData.value) {
          const browserTaskReceived = aguiData.value as BrowserTaskReceivedValue;
          const preferredToolName = typeof browserTaskReceived.tool === 'string' ? browserTaskReceived.tool : undefined;
          const toolCallId = findLatestCallingToolCallId(preferredToolName);
          if (toolCallId) {
            const toolCall = toolCallsRef.current.get(toolCallId);
            if (toolCall) {
              toolCall.browserTaskReceived = browserTaskReceived;
              syncActiveToolCallPanel(toolCallId, toolCall);
            }
          }
        }
        break;

      case 'ERROR':
      case 'RUN_ERROR':
        const errorMsg = aguiData.message || aguiData.error || 'Unknown error';
        setExecutionSummary({
          status: 'failed',
          title: t('chatflow.preview.failed'),
          reason: errorMsg,
        });
        setExecuteResult({
          isSSE: true,
          content: contentRef.current,
          toolCalls: new Map(toolCallsRef.current),
          error: errorMsg
        });
        return true;

      case 'RUN_FINISHED':
        setExecuteResult({
          isSSE: true,
          content: contentRef.current,
          toolCalls: new Map(toolCallsRef.current)
        });
        return true;
    }
    return false;
  }, [applyExecutionMeta, t]);

  const handleSSEExecution = useCallback(async (botId: string, nodeId: string, msg: string): Promise<'success' | 'aborted'> => {
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const contentRef = { current: '' };
    setStreamingContent('');
    toolCallsRef.current.clear();
    executionSnapshotRef.current = '';
    unchangedPollCountRef.current = 0;

    try {
      const url = getExecuteWorkflowSSEUrl(botId, nodeId);
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message: msg, is_test: true }),
        credentials: 'include',
        signal: abortController.signal,
      });

      const contentType = response.headers.get('Content-Type') || '';

      if (!contentType.includes('text/event-stream')) {
        const jsonData = await response.json();
        applyExecutionMeta(jsonData);
        if (!jsonData.result) {
          throw new Error(jsonData.message || 'Request failed');
        }
        setExecuteResult({
          isSSE: false,
          content: '',
          rawResponse: jsonData.data
        });
        return 'success';
      }

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Failed to get response reader');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          if (contentRef.current || toolCallsRef.current.size > 0) {
            setExecuteResult({
              isSSE: true,
              content: contentRef.current,
              toolCalls: new Map(toolCallsRef.current)
            });
          }
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
              setExecuteResult({
                isSSE: true,
                content: contentRef.current,
                toolCalls: new Map(toolCallsRef.current)
              });
              return 'success';
            }

            try {
              const parsedData: AGUIMessage = JSON.parse(dataStr);
              const shouldStop = handleAGUIMessage(parsedData, contentRef);
              if (shouldStop) {
                return 'success';
              }
            } catch (parseError) {
              console.warn('Failed to parse SSE chunk:', dataStr, parseError);
            }
          }
        }
      }
      return 'success';
    } catch (error: any) {
      if (error.name === 'AbortError') {
        return 'aborted';
      }
      throw error;
    } finally {
      abortControllerRef.current = null;
    }
  }, [token, getExecuteWorkflowSSEUrl, handleAGUIMessage, applyExecutionMeta]);

  const syncExecutionSummary = useCallback((details: WorkflowExecutionDetailItem[]) => {
    const failedNode = details.find((item) => item.status === 'failed');
    if (failedNode) {
      setExecutionSummary({
        status: 'failed',
        title: tRef.current('chatflow.preview.failed'),
        reason: failedNode.error_message,
      });
      return;
    }

    const hasRunningNode = details.some((item) => item.status === 'running' || item.status === 'pending');
    if (hasRunningNode) {
      setExecutionSummary({
        status: 'running',
        title: tRef.current('chatflow.preview.running'),
      });
      return;
    }

    if (details.length > 0) {
      setExecutionSummary({
        status: 'success',
        title: tRef.current('chatflow.preview.success'),
      });
    }
  }, []);

  const pollExecutionDetail = useCallback(async (executionId: string) => {
    if (!executionId || executionRequestInFlightRef.current) {
      return;
    }

    stopExecutionPolling();
    executionRequestInFlightRef.current = true;
    pollingExecutionIdRef.current = executionId;
    setExecutionDetailLoading(true);

    try {
      const details = await fetchExecutionDetailRef.current(executionId);

      if (pollingExecutionIdRef.current !== executionId) {
        return;
      }

      const sortedDetails = [...details].sort((left, right) => {
        const leftIndex = left.node_index ?? Number.MAX_SAFE_INTEGER;
        const rightIndex = right.node_index ?? Number.MAX_SAFE_INTEGER;
        return leftIndex - rightIndex;
      });

      setExecutionDetails(sortedDetails);
      const runningNode = sortedDetails.find((item) => item.status === 'running');
      const failedNode = sortedDetails.find((item) => item.status === 'failed');
      const latestCompletedNode = [...sortedDetails].reverse().find((item) => item.status === 'completed');
      setActiveExecutionNodeId(runningNode?.node_id || failedNode?.node_id || latestCompletedNode?.node_id || executeNodeIdRef.current || null);
      syncExecutionSummary(sortedDetails);

      const executionSnapshot = JSON.stringify(sortedDetails.map((item) => ({
        node_id: item.node_id,
        status: item.status,
        start_time: item.start_time,
        end_time: item.end_time,
        duration_ms: item.duration_ms,
        error_message: item.error_message,
      })));

      if (executionSnapshot === executionSnapshotRef.current) {
        unchangedPollCountRef.current += 1;
      } else {
        executionSnapshotRef.current = executionSnapshot;
        unchangedPollCountRef.current = 0;
      }

      const shouldContinuePolling = sortedDetails.some((item) => item.status === 'running' || item.status === 'pending');
      if (shouldContinuePolling) {
        const hasRunningNode = sortedDetails.some((item) => item.status === 'running');
        const pollInterval = hasRunningNode && unchangedPollCountRef.current === 0
          ? EXECUTION_POLL_BASE_INTERVAL
          : EXECUTION_POLL_SLOW_INTERVAL;

        executionPollTimerRef.current = window.setTimeout(() => {
          void pollExecutionDetail(executionId);
        }, pollInterval);
      } else {
        pollingExecutionIdRef.current = '';
      }
    } catch (error) {
      console.error('Failed to fetch execution detail:', error);
    } finally {
      executionRequestInFlightRef.current = false;
      setExecutionDetailLoading(false);
    }
  }, [stopExecutionPolling, syncExecutionSummary]);

  useEffect(() => {
    if (!latestExecutionId) {
      return;
    }

    void pollExecutionDetail(latestExecutionId);

    return () => {
      stopExecutionPolling();
    };
  }, [latestExecutionId, pollExecutionDetail, stopExecutionPolling]);

  const handleExecuteNode = useCallback(async () => {
    if (!executeNodeId) return;

    const getBotIdFromUrl = () => {
      if (typeof window !== 'undefined') {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('id') || '1';
      }
      return '1';
    };

    const botId = getBotIdFromUrl();

    setExecuteLoading(true);
    stopExecutionPolling();
    setExecuteResult(null);
    setStreamingContent('');
    setExecutionDetails([]);
    latestExecutionIdRef.current = '';
    setLatestExecutionId('');
    setExecutionSummary({
      status: 'running',
      title: t('chatflow.preview.running'),
    });
    setIsPreviewOpen(true);
    setIsExecuteDrawerVisible(false);
    toolCallsRef.current.clear();

    try {
      const status = await handleSSEExecution(botId, executeNodeId, executeMessage);
      if (status === 'success' && !latestExecutionIdRef.current) {
        setExecutionSummary({
          status: 'success',
          title: t('chatflow.preview.success'),
        });
        message.success(t('chatflow.executeSuccess'));
      }
    } catch (error: any) {
      console.error('Execute node error:', error);
      setExecutionSummary({
        status: 'failed',
        title: t('chatflow.preview.failed'),
        reason: error.message || t('chatflow.executeFailed'),
      });
      setExecuteResult({
        isSSE: false,
        content: '',
        error: error.message || t('chatflow.executeFailed')
      });
      message.error(t('chatflow.executeFailed'));
    } finally {
      setExecuteLoading(false);
    }
  }, [executeNodeId, executeMessage, handleSSEExecution, stopExecutionPolling, t]);

  const handleCloseDrawer = useCallback(() => {
    stopExecution();
    setIsExecuteDrawerVisible(false);
  }, [stopExecution]);

  useEffect(() => {
    return () => {
      stopExecutionPolling();
    };
  }, [stopExecutionPolling]);

  const executionStatusMap = executionDetails.reduce<Record<string, WorkflowExecutionDetailItem['status']>>((accumulator, item) => {
    accumulator[item.node_id] = item.status;
    return accumulator;
  }, {});

  const executionDurationMap = executionDetails.reduce<Record<string, number | null>>((accumulator, item) => {
    accumulator[item.node_id] = item.duration_ms;
    return accumulator;
  }, {});

  return {
    isExecuteDrawerVisible,
    setIsExecuteDrawerVisible,
    executeNodeId,
    executeMessage,
    setExecuteMessage,
    executeResult,
    executeLoading,
    streamingContent,
    handleExecuteNode,
    handleCloseDrawer,
    stopExecution,
    isPreviewOpen,
    openPreviewPanel,
    closePreviewPanel,
    executionDetailLoading,
    executionDetails,
    latestExecutionId,
    executionSummary,
    activeExecutionNodeId,
    executionStatusMap,
    executionDurationMap,
  };
};
