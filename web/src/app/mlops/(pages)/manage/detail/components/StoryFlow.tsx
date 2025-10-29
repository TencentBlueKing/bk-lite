import FlowWrapper from "@/app/mlops/components/flows/FlowProvider";
import { NodeType, TableData, NodeData } from '@/app/mlops/types';
import { Node, Edge } from "@xyflow/react";
import { message } from "antd";
import { useMemo, useState } from "react";
import { useTranslation } from "@/utils/i18n";
import useMlopsManageApi from "@/app/mlops/api/manage";

interface StoryFlowWrapperProps {
  dataset: string;
  backToList?: () => void;
  currentStory: TableData | null;
  onSuccess: () => void;
}

const StoryFlow: React.FC<StoryFlowWrapperProps> = ({
  dataset,
  // backToList,
  currentStory,
  onSuccess
}) => {
  const { t } = useTranslation();
  const { updateRasaStoryFile } = useMlopsManageApi();
  const [flowLoading, setFlowLoading] = useState<boolean>(false);
  const nodeTypes: NodeType[] = [
    { type: 'intent', label: t(`datasets.intentNode`), icon: 'tijiaoxiangfa' },
    { type: 'response', label: t(`datasets.responseNode`), icon: 'huifu-copy' },
    { type: 'slot', label: t(`datasets.slotNode`), icon: 'dangqianbianliang' },
    { type: 'form', label: t(`datasets.formNode`), icon: 'biaodan' },
    { type: 'action', label: t(`datasets.actionNode`), icon: 'dongzuo1' },
    { type: 'checkpoint', label: t(`datasets.checkpoint`), icon: 'fenzhi' },
  ];

  const [initialNodes, initialEdges] = useMemo(() => {
    if (currentStory) {
      // 节点处理
      const edgeMap = new Map();
      const edges: Edge[] = [];
      const nodes: Node<NodeData>[] = currentStory.steps?.map((item: any) => {
        if (item.source?.length) {
          item.source?.forEach((source: any) => {
            const edgeId = `${source?.id}-${item.id}`;
            if (!edgeMap.has(edgeId)) {
              edges.push({
                id: edgeId,
                type: 'buttonedge',
                source: item.id,
                target: source?.id,
                animated: true
              });
              edgeMap.set(edgeId, true);
            }
          })
        }
        if (item.target?.length) {
          item.target?.forEach((target: any) => {
            const edgeId = `${item.id}-${target?.id}`;
            if (!edgeMap.has(edgeId)) {
              edges.push({
                id: edgeId,
                type: 'buttonedge',
                source: target?.id,
                target: item.id,
                animated: true
              });
              edgeMap.set(edgeId, true);
            }
          })
        }

        return {
          id: item?.id,
          type: item?.type,
          position: item.position,
          data: {
            id: item?.id,
            type: item?.type,
            name: item?.name,
            source: item.source,
            target: item.target
          }
        };
      });
      return [nodes, edges];
    }
    return [[], []];
  }, [currentStory]);


  const updateStoryData = async (data: any) => {
    setFlowLoading(true);
    try {
      if (currentStory) {
        const steps = data.nodes.map((item: Node) => {
          return {
            id: item.id,
            name: item.data?.name || '',
            type: item.type,
            position: item.position,
            source: item.data?.source,
            target: item.data?.target,
          }
        });

        await updateRasaStoryFile(currentStory.id, {
          ...currentStory,
          steps
        });
        message.success(t('common.updateSuccess'));
        onSuccess();
      }
    } catch (e) {
      console.log(e);
      message.error(t(`common.updateFailed`));
    } finally {
      setFlowLoading(false);
    }
  };

  return (
    <FlowWrapper
      initialNodes={initialNodes}
      initialEdges={initialEdges}
      nodeTypes={nodeTypes}
      dataset={dataset}
      loading={flowLoading}
      handleSaveFlow={(data) => updateStoryData(data)}
    />
  )
};

export default StoryFlow