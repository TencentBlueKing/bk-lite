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
    { type: 'checkpoint', label: '检查点', icon: 'dongzuo1' },
  ];

  const [initialNodes, initialEdges] = useMemo(() => {
    if (currentStory) {
      // 节点处理
      const edgeMap = new Map();
      const edges: Edge[] = [];
      const nodes: Node<NodeData>[] = currentStory.steps?.map((item: any) => {
        if (item.source?.length) {
          item.source?.forEach((source: string) => {
            const edgeId = `${source}-${item.id}`;
            if (!edgeMap.has(edgeId)) {
              edges.push({
                id: edgeId,
                source: item.id,
                target: source,
                animated: true
              });
              edgeMap.set(edgeId, true);
            }
          })
        }
        if (item.target?.length) {
          item.target?.forEach((target: string) => {
            const edgeId = `${item.id}-${target}`;
            if (!edgeMap.has(edgeId)) {
              edges.push({
                id: edgeId,
                source: target,
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
            name: item?.name,
            source: item.source,
            target: item.target
          }
        };
      });
      console.log(nodes, edges);
      return [nodes, edges];
    }
    return [[], []];
  }, [currentStory]);


  const updateStoryData = async (data: any) => {
    console.log(data);
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
      // panel={[
      //   <Button key="back" size="small" variant="outlined" className="mr-2 text-xs" onClick={backToList}>{t(`mlops-common.backToList`)}</Button>,
      // ]}
      handleSaveFlow={(data) => updateStoryData(data)}
    />
  )
};

export default StoryFlow