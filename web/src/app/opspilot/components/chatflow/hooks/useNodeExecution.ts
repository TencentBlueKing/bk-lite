import { useEffect, useCallback, useState, useRef } from 'react';
import { message } from 'antd';
import { useSession } from 'next-auth/react';
import { useAuth } from '@/context/auth';
import { useStudioApi } from '../../../api/studio';
import { AGUIMessage } from '@/app/opspilot/types/chat';
import { ToolCallInfo } from '../../custom-chat-sse/toolCallRenderer';

export interface NodeExecutionResult {
  isSSE: boolean;
  content: string;
  toolCalls?: Map<string, ToolCallInfo>;
  rawResponse?: any;
  error?: string;
}

export const useNodeExecution = (t: any) => {
  const { getExecuteWorkflowSSEUrl } = useStudioApi();
  
  const { data: session } = useSession();
  const authContext = useAuth();
  const token = session?.user?.token || authContext?.token || null;
  
  const [isExecuteDrawerVisible, setIsExecuteDrawerVisible] = useState(false);
  const [executeNodeId, setExecuteNodeId] = useState<string>('');
  const [executeMessage, setExecuteMessage] = useState<string>('');
  const [executeResult, setExecuteResult] = useState<NodeExecutionResult | null>(null);
  const [executeLoading, setExecuteLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string>('');
  
  const abortControllerRef = useRef<AbortController | null>(null);
  const toolCallsRef = useRef<Map<string, ToolCallInfo>>(new Map());

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

  const stopExecution = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setExecuteLoading(false);
  }, []);

  const handleAGUIMessage = useCallback((aguiData: AGUIMessage, contentRef: { current: string }) => {
    switch (aguiData.type) {
      case 'RUN_STARTED':
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
          }
        }
        break;

      case 'ERROR':
      case 'RUN_ERROR':
        const errorMsg = aguiData.message || aguiData.error || 'Unknown error';
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
  }, []);

  const handleSSEExecution = useCallback(async (botId: string, nodeId: string, msg: string): Promise<'success' | 'aborted'> => {
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    
    const contentRef = { current: '' };
    setStreamingContent('');
    toolCallsRef.current.clear();

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
  }, [token, getExecuteWorkflowSSEUrl, handleAGUIMessage]);

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
    setExecuteResult(null);
    setStreamingContent('');
    toolCallsRef.current.clear();

    try {
      const status = await handleSSEExecution(botId, executeNodeId, executeMessage);
      if (status === 'success') {
        message.success(t('chatflow.executeSuccess'));
      }
    } catch (error: any) {
      console.error('Execute node error:', error);
      setExecuteResult({
        isSSE: false,
        content: '',
        error: error.message || t('chatflow.executeFailed')
      });
      message.error(t('chatflow.executeFailed'));
    } finally {
      setExecuteLoading(false);
    }
  }, [executeNodeId, executeMessage, handleSSEExecution, t]);

  const handleCloseDrawer = useCallback(() => {
    stopExecution();
    setIsExecuteDrawerVisible(false);
    setExecuteResult(null);
    setStreamingContent('');
    toolCallsRef.current.clear();
  }, [stopExecution]);

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
  };
};
