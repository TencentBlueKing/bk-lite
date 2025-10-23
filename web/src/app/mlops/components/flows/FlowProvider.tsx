import React from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import NodeFlow from './NodeFlow';
import { Node, Edge } from '@xyflow/react';
import { NodeType, NodeData } from '@/app/mlops/types';
import { Spin } from 'antd';
import flowStyle from './index.module.scss';

interface FlowWrapperProps {
  initialNodes: Node<NodeData>[];
  initialEdges: Edge[];
  nodeTypes: NodeType[];
  dataset: string;
  panel?: React.ReactNode[];
  loading: boolean;
  handleSaveFlow: (data: any) => void
}

const FlowWrapper: React.FC<FlowWrapperProps> = ({
  initialNodes,
  initialEdges,
  nodeTypes,
  dataset,
  panel = [],
  loading,
  handleSaveFlow
}) => {
  return (
    <ReactFlowProvider>
      <div className={`${flowStyle.flowContainer}`}>
        <Spin spinning={loading}>
          <NodeFlow
            nodeTypes={nodeTypes}
            dataset={dataset}
            initialNodes={initialNodes}
            initialEdges={initialEdges}
            panel={panel}
            handleSaveFlow={handleSaveFlow}
          />
        </Spin>
      </div>
    </ReactFlowProvider>
  );
};

export default FlowWrapper;