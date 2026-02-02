import { useCallback } from 'react';
import type { Node, Edge } from '@xyflow/react';

const NODE_WIDTH = 240;
const NODE_HEIGHT = 120;
const HORIZONTAL_GAP = 100;
const VERTICAL_GAP = 80;
const GRID_SIZE = 20; // 网格大小，用于对齐

type LayoutDirection = 'TB' | 'LR';

interface LayoutOptions {
  direction?: LayoutDirection;
  nodeWidth?: number;
  nodeHeight?: number;
  horizontalGap?: number;
  verticalGap?: number;
}

interface UseAutoLayoutReturn {
  getLayoutedElements: (
    nodes: Node[],
    edges: Edge[],
    options?: LayoutOptions
  ) => Promise<{ nodes: Node[]; edges: Edge[] }>;
}

// 对齐到网格
const snapToGrid = (value: number, gridSize: number): number => {
  return Math.round(value / gridSize) * gridSize;
};

// 计算节点层级（基于拓扑排序）
const calculateNodeLevels = (nodes: Node[], edges: Edge[]): Map<string, number> => {
  const levels = new Map<string, number>();
  const inDegree = new Map<string, number>();
  const adjList = new Map<string, string[]>();
  
  // 初始化
  nodes.forEach(node => {
    inDegree.set(node.id, 0);
    adjList.set(node.id, []);
    levels.set(node.id, 0);
  });
  
  // 构建邻接表和入度
  edges.forEach(edge => {
    adjList.get(edge.source)?.push(edge.target);
    inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1);
  });
  
  // BFS 层次遍历
  const queue: string[] = [];
  nodes.forEach(node => {
    if (inDegree.get(node.id) === 0) {
      queue.push(node.id);
      levels.set(node.id, 0);
    }
  });
  
  while (queue.length > 0) {
    const nodeId = queue.shift()!;
    const currentLevel = levels.get(nodeId) || 0;
    
    adjList.get(nodeId)?.forEach(targetId => {
      const newLevel = currentLevel + 1;
      levels.set(targetId, Math.max(levels.get(targetId) || 0, newLevel));
      
      inDegree.set(targetId, (inDegree.get(targetId) || 0) - 1);
      if (inDegree.get(targetId) === 0) {
        queue.push(targetId);
      }
    });
  }
  
  return levels;
};

export const useAutoLayout = (): UseAutoLayoutReturn => {
  const getLayoutedElements = useCallback(
    async (nodes: Node[], edges: Edge[], options: LayoutOptions = {}) => {
      console.log('[useAutoLayout] Starting layout with', nodes.length, 'nodes and', edges.length, 'edges');
      
      const {
        direction = 'LR',
        nodeWidth = NODE_WIDTH,
        nodeHeight = NODE_HEIGHT,
        horizontalGap = HORIZONTAL_GAP,
        verticalGap = VERTICAL_GAP,
      } = options;

      try {
        console.log('[useAutoLayout] Using custom layout algorithm...');
        
        // 计算每个节点的层级
        const levels = calculateNodeLevels(nodes, edges);
        console.log('[useAutoLayout] Node levels calculated');
        
        // 按层级分组节点
        const nodesByLevel = new Map<number, Node[]>();
        nodes.forEach(node => {
          const level = levels.get(node.id) || 0;
          if (!nodesByLevel.has(level)) {
            nodesByLevel.set(level, []);
          }
          nodesByLevel.get(level)!.push(node);
        });
        
        const isHorizontal = direction === 'LR';
        const layoutedNodes: Node[] = [];
        
        // 为每一层的节点计算位置
        nodesByLevel.forEach((nodesInLevel, level) => {
          const levelNodeCount = nodesInLevel.length;
          
          nodesInLevel.forEach((node, indexInLevel) => {
            const width = node.measured?.width ?? nodeWidth;
            const height = node.measured?.height ?? nodeHeight;
            
            let x: number, y: number;
            
            if (isHorizontal) {
              // 水平布局：level 决定 X，indexInLevel 决定 Y
              x = level * (width + horizontalGap);
              // 居中对齐同层节点
              const totalHeight = levelNodeCount * height + (levelNodeCount - 1) * verticalGap;
              const startY = -totalHeight / 2;
              y = startY + indexInLevel * (height + verticalGap) + height / 2;
            } else {
              // 垂直布局：level 决定 Y，indexInLevel 决定 X
              y = level * (height + verticalGap);
              // 居中对齐同层节点
              const totalWidth = levelNodeCount * width + (levelNodeCount - 1) * horizontalGap;
              const startX = -totalWidth / 2;
              x = startX + indexInLevel * (width + horizontalGap) + width / 2;
            }
            
            layoutedNodes.push({
              ...node,
              position: {
                x: snapToGrid(x, GRID_SIZE),
                y: snapToGrid(y, GRID_SIZE),
              },
            });
          });
        });

        console.log('[useAutoLayout] Layout complete, returning', layoutedNodes.length, 'nodes');
        return { nodes: layoutedNodes, edges };
      } catch (error) {
        console.error('[useAutoLayout] Error during layout:', error);
        return { nodes, edges };
      }
    },
    []
  );

  return { getLayoutedElements };
};
