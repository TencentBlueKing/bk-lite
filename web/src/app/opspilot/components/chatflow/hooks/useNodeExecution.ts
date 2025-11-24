import { useEffect, useCallback, useState } from 'react';
import { message } from 'antd';
import { useStudioApi } from '../../../api/studio';

export const useNodeExecution = (t: any) => {
  const { executeWorkflow } = useStudioApi();
  const [isExecuteDrawerVisible, setIsExecuteDrawerVisible] = useState(false);
  const [executeNodeId, setExecuteNodeId] = useState<string>('');
  const [executeMessage, setExecuteMessage] = useState<string>('');
  const [executeResult, setExecuteResult] = useState<any>(null);
  const [executeLoading, setExecuteLoading] = useState(false);

  useEffect(() => {
    const handleExecuteNode = (event: any) => {
      const { nodeId } = event.detail;
      setExecuteNodeId(nodeId);
      setExecuteMessage('');
      setExecuteResult(null);
      setIsExecuteDrawerVisible(true);
    };

    window.addEventListener('executeNode', handleExecuteNode);
    return () => {
      window.removeEventListener('executeNode', handleExecuteNode);
    };
  }, []);

  const handleExecuteNode = useCallback(async () => {
    if (!executeNodeId) return;

    const getBotIdFromUrl = () => {
      if (typeof window !== 'undefined') {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('id') || '1';
      }
      return '1';
    };

    setExecuteLoading(true);
    try {
      const response = await executeWorkflow({
        message: executeMessage,
        bot_id: getBotIdFromUrl(),
        node_id: executeNodeId,
      });

      setExecuteResult(response);
      message.success(t('chatflow.executeSuccess'));
    } catch (error) {
      console.error('Execute node error:', error);
      message.error(t('chatflow.executeFailed'));
    } finally {
      setExecuteLoading(false);
    }
  }, [executeNodeId, executeMessage, executeWorkflow, t]);

  return {
    isExecuteDrawerVisible,
    setIsExecuteDrawerVisible,
    executeNodeId,
    executeMessage,
    setExecuteMessage,
    executeResult,
    executeLoading,
    handleExecuteNode,
  };
};
