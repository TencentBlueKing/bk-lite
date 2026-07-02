import { useCallback, useRef, useEffect } from 'react';
import { message } from 'antd';
import type { Node, Edge } from '@xyflow/react';
import type { ChatflowNodeData } from '../types';
import { getDefaultConfig } from '@/app/opspilot/constants/chatflow';

interface UseNodeDropProps {
  reactFlowInstance: any;
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>;
  edges: Edge[];
  onSave?: (nodes: Node[], edges: Edge[]) => void;
  t: any;
}

export const useNodeDrop = ({
  reactFlowInstance,
  setNodes,
  edges,
  onSave,
  t,
}: UseNodeDropProps) => {
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent, reactFlowWrapper: React.RefObject<HTMLDivElement>) => {
      event.preventDefault();

      try {
        const reactFlowBounds = reactFlowWrapper.current?.getBoundingClientRect();
        const type = event.dataTransfer.getData('application/reactflow');

        if (!type || !reactFlowBounds || !reactFlowInstance) {
          return;
        }

        const mouseX = event.clientX - reactFlowBounds.left;
        const mouseY = event.clientY - reactFlowBounds.top;

        if (mouseX < 0 || mouseY < 0 || mouseX > reactFlowBounds.width || mouseY > reactFlowBounds.height) {
          return;
        }

        const flowPosition = reactFlowInstance.screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });

        const nodeWidth = 240;
        const nodeHeight = 120;

        const adjustedPosition = {
          x: flowPosition.x - nodeWidth / 2,
          y: flowPosition.y - nodeHeight / 2,
        };

        const getNodeLabel = (nodeType: string) => {
          try {
            if (nodeType === 'enterprise_wechat') {
              return t('chatflow.enterpriseWechat');
            }
            if (nodeType === 'enterprise_wechat_aibot') {
              return t('chatflow.enterpriseWechatAibot');
            }
            if (nodeType === 'nats') {
              return t('chatflow.nats');
            }
            if (nodeType === 'dingtalk') {
              return t('chatflow.dingtalk');
            }
            if (nodeType === 'wechat_official') {
              return t('chatflow.wechatOfficial');
            }
            if (nodeType === 'embedded_chat') {
              return t('chatflow.embeddedChat');
            }
            if (nodeType === 'web_chat') {
              return t('chatflow.webChat');
            }
            if (nodeType === 'mobile') {
              return t('chatflow.mobile');
            }
            if (nodeType === 'intent_classification') {
              return t('chatflow.intentClassification');
            }
            if (nodeType === 'memory_read') {
              return t('chatflow.memoryRead');
            }
            if (nodeType === 'memory_write') {
              return t('chatflow.memoryWrite');
            }
            return t(`chatflow.${nodeType}`);
          } catch {
            return nodeType;
          }
        };

        const newNode: Node = {
          id: `${type}-${Date.now()}`,
          type,
          position: adjustedPosition,
          data: {
            label: getNodeLabel(type),
            type: type as ChatflowNodeData['type'],
            config: getDefaultConfig(type),
            description: ''
          },
        };

        setNodes((nds) => {
          let nodeToAdd = newNode;
          // nats 触发节点多次拖出时自动改名（NATS触发、NATS触发 1…），
          // 保证后端按「BOT名 - 节点名」生成的通道名不冲突
          if (type === 'nats') {
            const baseLabel = getNodeLabel('nats');
            const existingLabels = new Set(
              nds
                .filter((n) => n.type === 'nats')
                .map((n) => (n.data as ChatflowNodeData | undefined)?.label)
            );
            let uniqueLabel = baseLabel;
            let suffix = 1;
            while (existingLabels.has(uniqueLabel)) {
              uniqueLabel = `${baseLabel} ${suffix}`;
              suffix += 1;
            }
            nodeToAdd = { ...newNode, data: { ...newNode.data, label: uniqueLabel } };
          }
          const updatedNodes = nds.concat(nodeToAdd);

          if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
          saveTimerRef.current = setTimeout(() => {
            if (onSave) {
              onSave(updatedNodes, edges);
            }
          }, 50);

          return updatedNodes;
        });
      } catch (error) {
        console.error('Drag and drop error:', error);
        message.error(t('chatflow.messages.dragFailed'));
      }
    },
    [reactFlowInstance, setNodes, edges, onSave, t]
  );

  return { onDragOver, onDrop };
};
