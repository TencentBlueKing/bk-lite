import { useCallback } from 'react';
import { Modal, message } from 'antd';
import type { Node, Edge } from '@xyflow/react';

interface UseNodeDeletionProps {
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>;
  setEdges: React.Dispatch<React.SetStateAction<Edge[]>>;
  setSelectedNodes: React.Dispatch<React.SetStateAction<Node[]>>;
  setSelectedEdges: React.Dispatch<React.SetStateAction<Edge[]>>;
  setIsConfigDrawerVisible: React.Dispatch<React.SetStateAction<boolean>>;
  selectedNodes: Node[];
  selectedEdges: Edge[];
  t: any;
}

export const useNodeDeletion = ({
  setNodes,
  setEdges,
  setSelectedNodes,
  setSelectedEdges,
  setIsConfigDrawerVisible,
  selectedNodes,
  selectedEdges,
  t,
}: UseNodeDeletionProps) => {
  const handleDeleteNode = useCallback((nodeId: string) => {
    Modal.confirm({
      title: t('chatflow.messages.deleteConfirm'),
      onOk: () => {
        setNodes((nds) => nds.filter((n) => n.id !== nodeId));
        setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
        setIsConfigDrawerVisible(false);
        message.success(t('chatflow.messages.nodeDeleted'));
      }
    });
  }, [setNodes, setEdges, setIsConfigDrawerVisible, t]);

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if ((event.key === 'Delete' || event.key === 'Backspace') && (selectedNodes.length > 0 || selectedEdges.length > 0)) {
      event.preventDefault();

      const hasNodes = selectedNodes.length > 0;

      if (hasNodes) {
        const currentSelectedNodes = [...selectedNodes];
        const currentSelectedEdges = [...selectedEdges];

        let title = '';
        let content = '';

        if (currentSelectedNodes.length === 1) {
          const nodeToDelete = currentSelectedNodes[0];
          title = t('chatflow.messages.deleteConfirm');
          content = `${t('chatflow.messages.deleteNodeContent')} ${nodeToDelete.data.label}`;
        } else {
          title = t('chatflow.messages.deleteMultipleConfirm');
          content = `${t('chatflow.messages.deleteMultipleContent')} ${currentSelectedNodes.length}`;
        }

        Modal.confirm({
          title,
          content,
          okText: t('common.confirm'),
          cancelText: t('common.cancel'),
          okButtonProps: { danger: true },
          onOk: () => {
            const selectedNodeIds = currentSelectedNodes.map(node => node.id);
            setNodes((nds) => nds.filter((n) => !selectedNodeIds.includes(n.id)));
            setEdges((eds) => eds.filter((e) => !selectedNodeIds.includes(e.source) && !selectedNodeIds.includes(e.target)));

            if (currentSelectedEdges.length > 0) {
              const selectedEdgeIds = currentSelectedEdges.map(edge => edge.id);
              setEdges((eds) => eds.filter((e) => !selectedEdgeIds.includes(e.id)));
            }

            setSelectedNodes([]);
            setSelectedEdges([]);
            setIsConfigDrawerVisible(false);

            if (currentSelectedEdges.length > 0) {
              message.success(`${t('chatflow.messages.itemsDeleted')} ${currentSelectedNodes.length} ${t('chatflow.messages.nodes')} ${currentSelectedEdges.length} ${t('chatflow.messages.edges')}`);
            } else {
              message.success(`${t('chatflow.messages.multipleNodesDeleted')} ${currentSelectedNodes.length}`);
            }
          },
        });
      } else if (selectedEdges.length > 0) {
        const selectedEdgeIds = selectedEdges.map(edge => edge.id);
        setEdges((eds) => eds.filter((e) => !selectedEdgeIds.includes(e.id)));
        setSelectedEdges([]);
        message.success(`${t('chatflow.messages.edgesDeleted')} ${selectedEdges.length}`);
      }
    }
  }, [selectedNodes, selectedEdges, setNodes, setEdges, setSelectedNodes, setSelectedEdges, setIsConfigDrawerVisible, t]);

  return { handleDeleteNode, handleKeyDown };
};
