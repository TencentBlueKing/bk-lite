import React from 'react';
import { BaseEdge, getBezierPath, type EdgeProps, EdgeLabelRenderer, useReactFlow, Node } from "@xyflow/react";
import { Button } from "antd";
import { CloseOutlined } from "@ant-design/icons";
import { NodeData } from '@/app/mlops/types';

const CustomEdge = ({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  selected = false
}: EdgeProps) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition
  });

  const { setEdges, setNodes } = useReactFlow<Node<NodeData>>();
  const onEdgesClick = () => {
    setEdges((edges) => edges.filter((edge) => edge.id !== id));
    setNodes(
      (prev) =>
        prev.map(
          (item) => {
            return {
              ...item,
              data: {
                ...item.data,
                source: item.data?.source.filter((item: any) => item?.id !== target),
                target: item.data?.target.filter((item: any) => item?.id !== source),
              }
            }
          }
        )
    );
  };

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        {selected && (
          <div className='absolute pointer-events-auto origin-center' style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
          }}>
            <Button type="default" size='small' className='rounded-[50%] opacity-60 hover:opacity-100 transition-opacity' icon={<CloseOutlined />} onClick={onEdgesClick} />
          </div>
        )}
      </EdgeLabelRenderer>
    </>
  )
};

export default CustomEdge;